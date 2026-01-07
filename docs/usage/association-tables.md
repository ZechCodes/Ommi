# Using Association Tables for Many-to-Many Relationships

Many-to-many relationships (e.g., a `Student` can enroll in multiple `Courses`, and a `Course` can have many `Students`) are typically modeled using an intermediary **association table** (or join table).

Ommi handles this by combining **Query Fields** with an explicit association model. You use `LazyList` along with `typing.Annotated` and `ommi.models.query_fields.AssociateUsing` to define these relationships.

## Defining Models for a Many-to-Many Relationship

You'll define three models:
1.  The first primary model (e.g., `Post`).
2.  The second primary model (e.g., `Tag`).
3.  The association model that links them (e.g., `PostTag`), which contains foreign keys to `Post` and `Tag`.

**Example from Ommi's tests (adapted for Post/Tag scenario):**

Imagine `Post`s can have multiple `Tag`s, and `Tag`s can be applied to multiple `Post`s.

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated, List, Optional

from ommi import Ommi, ommi_model
from ommi.models.collections import ModelCollection
from ommi.models.field_metadata import ReferenceTo
from ommi.models.query_fields import AssociateUsing, LazyList
from ommi.query_ast import where # Not strictly needed for M2M definition, but good for other queries
from ommi.ext.drivers.sqlite import SQLiteDriver

app_models = ModelCollection()

@ommi_model(collection=app_models)
@dataclass
class Post:
    id: int
    title: str

    # Query Field for fetching all related Tags for this Post
    # It uses LazyList with an Annotated type.
    # AssociateUsing(PostTag) tells Ommi to use the PostTag model as the intermediary.
    # Ommi infers the join conditions from the foreign keys in PostTag.
    tags: "LazyList[Annotated[Tag, AssociateUsing(PostTag)]]"

@ommi_model(collection=app_models)
@dataclass
class Tag:
    id: int
    name: str

    # Optional: Define the reverse relationship from Tag to Post
    # posts: "LazyList[Annotated[Post, AssociateUsing(PostTag)]]"

@ommi_model(collection=app_models)
@dataclass
class PostTag: # The Association Table
    # By convention, Ommi might use fields like 'post_id' and 'tag_id'
    # to understand the links if ReferenceTo is more complex for M2M linking fields.
    # The test_query_fields.py example uses ReferenceTo(ModelA.id) directly in the association table.
    post_id: Annotated[int, ReferenceTo(Post.id)]
    tag_id: Annotated[int, ReferenceTo(Tag.id)]
    # You can add other fields to the association table, e.g., timestamp
    created_at: Optional[str] = None

    # Ommi might require a way to specify composite primary keys if 'post_id' and 'tag_id' together form one.
    # For now, assume Ommi handles this or they are just indexed.


async def demo_many_to_many():
    driver = SQLiteDriver.connect()
    async with Ommi(driver) as db:
        await app_models.setup_on(db) # Creates Post, Tag, PostTag tables

        # Create data
        post1 = Post(id=1, title="Ommi is Great")
        post2 = Post(id=2, title="Python Tips")
        tag_ommi = Tag(id=101, name="ommi")
        tag_python = Tag(id=102, name="python")
        tag_guide = Tag(id=103, name="guide")

        await db.add(post1, post2, tag_ommi, tag_python, tag_guide).or_raise()

        # Create associations in PostTag table
        # Post1 is tagged with "ommi" and "guide"
        await db.add(
            PostTag(post_id=post1.id, tag_id=tag_ommi.id, created_at="2024-01-01"),
            PostTag(post_id=post1.id, tag_id=tag_guide.id, created_at="2024-01-01")
        ).or_raise()

        # Post2 is tagged with "python" and "guide"
        await db.add(
            PostTag(post_id=post2.id, tag_id=tag_python.id, created_at="2024-01-02"),
            PostTag(post_id=post2.id, tag_id=tag_guide.id, created_at="2024-01-02")
        ).or_raise()

        # --- Lazily load tags for a post ---
        retrieved_post1 = await db.find(Post.id == 1).one.or_raise()
        print(f"Post: '{retrieved_post1.title}'")

        print("Loading tags for Post 1...")
        post1_tags = await retrieved_post1.tags # This triggers the lazy load

        print(f"Tags for '{retrieved_post1.title}':")
        for tag in post1_tags:
            print(f"- {tag.name}")
        
        # --- (Optional) Lazily load posts for a tag (if reverse relationship is defined) ---
        # retrieved_tag_guide = await db.find(Tag.id == tag_guide.id).one.or_raise()
        # print(f"\nTag: '{retrieved_tag_guide.name}'")
        # print(f"Loading posts for Tag '{retrieved_tag_guide.name}'...")
        # guide_posts = await retrieved_tag_guide.posts
        # print(f"Posts tagged with '{retrieved_tag_guide.name}':")
        # for post in guide_posts:
        #     print(f"- {post.title}")

        await app_models.remove_from(db)

# To run:
# if __name__ == "__main__":
#     asyncio.run(demo_many_to_many())
```

## How Ommi Handles Many-to-Many

1.  **Association Model (`PostTag`):** This model is crucial. It explicitly defines the links between `Post` and `Tag` using foreign keys (defined with `Annotated[int, ReferenceTo(Model.id)]`).
2.  **Query Field on Primary Model (`Post.tags`):**
    *   It's typed with `LazyList` because a post can have multiple tags.
    *   Inside `LazyList`, `Annotated[Tag, AssociateUsing(PostTag)]` is used.
        *   `Tag`: Specifies that the query field will return instances of `Tag`.
        *   `AssociateUsing(PostTag)`: Tells Ommi that `PostTag` is the intermediary table to use for resolving this relationship.
3.  **Lazy Loading:** When you `await post_instance.tags`, Ommi:
    *   Identifies `post_instance` (e.g., Post with id=1).
    *   Looks at the `PostTag` table.
    *   Finds all `PostTag` records where `post_id` matches `post_instance.id`.
    *   For each of these `PostTag` records, it takes the `tag_id`.
    *   It then fetches all `Tag` models corresponding to these `tag_id`s.
    *   Returns a list of these `Tag` instances.

This provides a declarative way to define complex many-to-many relationships, with Ommi handling the underlying join logic through the association table when the query field is awaited.

## Key Aspects

*   **Explicit Association Model:** You *must* define the association model (e.g., `PostTag`). This model can also hold additional attributes about the relationship itself (e.g., `created_at` timestamp).
*   **`AssociateUsing`:** This is the key to linking the `LazyList` query field to the correct association table.
*   **`ReferenceTo`:** Used in the association model to define the foreign keys linking back to the primary models.
*   **Bidirectional Relationships:** You can define the relationship on both sides (e.g., `Post.tags` and `Tag.posts`) using the same `AssociateUsing(PostTag)` mechanism.

This approach keeps your model definitions clean while leveraging Ommi's query field system for efficient, lazy-loaded data retrieval for many-to-many relationships. 