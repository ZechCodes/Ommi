# Understanding Lazy Fields (Query Fields)

Ommi handles lazy loading of related data through a powerful feature called **Query Fields**. These allow you to define model attributes that represent relationships to other models. The data for these related models is not fetched immediately when the parent object is loaded; instead, it's retrieved (lazily) only when you explicitly `await` the query field attribute.

This approach is excellent for:

*   **Performance:** Avoiding the overhead of complex joins and loading large related object graphs by default.
*   **Clarity:** Defining relationships directly within your models using expressive type annotations. Ommi infers the join conditions from `ReferenceTo` annotations on your foreign key fields.

## Types of Query Fields for Lazy Loading

Ommi provides specialized types within `ommi.models.query_fields` to define different kinds of lazy-loaded relationships:

*   **`LazyLoadTheRelated[TargetModelType]`**: For one-to-one or many-to-one relationships. When awaited, it fetches a single instance of `TargetModelType` or `None`.
*   **`LazyLoadEveryRelated[TargetModelType]`**: For one-to-many or many-to-many relationships. When awaited, it fetches a list of `TargetModelType` instances.

These types are typically used in conjunction with `typing.Annotated` and `ommi.models.field_metadata.ReferenceTo` (for foreign keys). For many-to-many relationships, `ommi.models.query_fields.AssociateUsing` is also involved, as shown in the [Association Tables](association-tables.md) guide.

## Defining and Using Lazy Fields

Here's how you can define and use lazy-loaded query fields:

### 1. One-to-One / Many-to-One Relationships

Imagine a `Comment` model that relates to a single `Article`. Ommi will infer how to join `Comment` to `Article` based on the `article_id` field having a `ReferenceTo(Article)` annotation.

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated, Optional

from ommi import Ommi, ommi_model
from ommi.models.collections import ModelCollection
from ommi.models.field_metadata import ReferenceTo
from ommi.models.query_fields import LazyLoadTheRelated
# `when` is not needed for basic inferred joins but useful for custom queries.
# from ommi.query_ast import when
from ommi.ext.drivers.sqlite import SQLiteDriver # Example driver

app_models = ModelCollection()

@ommi_model(collection=app_models)
@dataclass
class Article:
    id: int
    title: str

@ommi_model(collection=app_models)
@dataclass
class Comment:
    id: int
    text: str
    # This field provides the link for Ommi to infer the join for `article` query field.
    article_id: Annotated[int, ReferenceTo(Article)] # Foreign Key to Article

    # Query field to lazily load the related Article.
    # Ommi infers the join condition using `article_id` and its `ReferenceTo(Article)`.
    article: "LazyLoadTheRelated[Article]"


async def demo_one_to_one_lazy_load():
    driver = SQLiteDriver.connect() # In-memory SQLite for example
    async with Ommi(driver) as db:
        await app_models.setup_on(db)

        # Create sample data
        article_1 = Article(id=1, title="Understanding Ommi")
        comment_1 = Comment(id=101, text="Great article!", article_id=article_1.id)
        await db.add(article_1, comment_1).or_raise()

        # Fetch a comment
        retrieved_comment = await db.find(Comment.id == 101).one.or_raise()
        print(f"Comment: '{retrieved_comment.text}' (Article ID: {retrieved_comment.article_id})")

        # At this point, `retrieved_comment.article` has not been loaded from the DB.
        # To load it, await the query field:
        print("Lazily loading related article...")
        related_article_instance = await retrieved_comment.article

        if related_article_instance:
            print(f"Belongs to Article (loaded lazily): '{related_article_instance.title}' (ID: {related_article_instance.id})")
        else:
            print("Could not load related article.")

        await app_models.remove_from(db)

# To run:
# if __name__ == "__main__":
#     asyncio.run(demo_one_to_one_lazy_load())
```

### 2. One-to-Many Relationships

An `Article` can have multiple `Comment`s. Ommi infers this relationship by finding `Comment` models that have a foreign key (`article_id`) pointing back to the `Article`.

```python
# (Continuing from previous example, ensure Article and Comment models are defined)
# Ensure necessary imports are present: LazyLoadEveryRelated
# from ommi.models.query_fields import LazyLoadEveryRelated

@ommi_model(collection=app_models) # Assuming app_models and Comment are already defined
@dataclass
class Article:
    id: int
    title: str

    # Query field to lazily load all related Comments for this Article.
    # Ommi infers that it needs to find Comments where Comment.article_id == self.id
    # based on the ReferenceTo(Article) in the Comment model.
    comments: "LazyLoadEveryRelated[Comment]"


async def demo_one_to_many_lazy_load():
    driver = SQLiteDriver.connect()
    async with Ommi(driver) as db:
        await app_models.setup_on(db) # Ensure tables for Article, Comment exist

        # Create sample data
        article_2 = Article(id=2, title="Ommi Query Fields")
        # Ensure Comment is defined as in the previous example for this to work seamlessly
        comment_2a = Comment(id=201, text="Very cool!", article_id=article_2.id)
        comment_2b = Comment(id=202, text="Super useful.", article_id=article_2.id)
        comment_2c = Comment(id=203, text="Needs more examples.", article_id=999) # Unrelated comment

        await db.add(article_2, comment_2a, comment_2b, comment_2c).or_raise()

        # Fetch an article
        retrieved_article = await db.find(Article.id == 2).one.or_raise()
        print(f"Article: '{retrieved_article.title}'")

        # Load its comments lazily
        print("Lazily loading comments...")
        related_comments_list = await retrieved_article.comments

        print(f"Found {len(related_comments_list)} comments for '{retrieved_article.title}' (loaded lazily):")
        for c in related_comments_list:
            print(f"- '{c.text}' (ID: {c.id}, ArticleID: {c.article_id})")

        await app_models.remove_from(db)

# To run:
# if __name__ == "__main__":
#     asyncio.run(demo_one_to_many_lazy_load())
```

## How it Works

When you define an attribute like `article: "LazyLoadTheRelated[Article]"` on your `Comment` model:

1.  Ommi recognizes this as a query field during model processing.
2.  It inspects the `Comment` model for fields that have a `ReferenceTo(Article)` annotation (in this case, `Comment.article_id`).
3.  This foreign key relationship informs Ommi how to construct the query to fetch the related `Article` for a given `Comment` instance (i.e., `WHERE Article.id == comment_instance.article_id`).
4.  When an instance of `Comment` is created, the `article` attribute becomes an instance of `LazyLoadTheRelated`.
5.  This object holds the context needed (like the parent `Comment` instance's ID and the inferred join condition) and has access to the database driver.
6.  When you `await` this attribute (e.g., `await retrieved_comment.article`), it executes the inferred query to fetch the related `Article` data.

A similar process occurs for `LazyLoadEveryRelated[Comment]` on the `Article` model, where Ommi looks for `Comment` models referencing the `Article`.

This inference mechanism provides a clean and Pythonic way to declare and use lazily-loaded relationships, minimizing explicit query definitions for common relationship patterns.

## Considerations

*   **`ReferenceTo` is Key:** The accuracy of your `ReferenceTo` annotations on foreign key fields is crucial for Ommi to correctly infer the join conditions.
*   **Async Await:** Remember that accessing the data from a query field is an asynchronous operation, so you must `await` it.
*   **N+1 Problem:** If you iterate over a list of objects and `await` a query field for each one inside the loop, you will issue multiple database queries (N+1). If you need to load related data for many objects at once, look for mechanisms in Ommi that might allow for eager loading or prefetching these relationships (this specific feature for optimizing N+1 is not detailed in the reviewed test files but is common in ORMs).

Next, see how this simplified approach applies to [Association Tables](association-tables.md) for many-to-many relationships, where `AssociateUsing` helps guide the inference. 