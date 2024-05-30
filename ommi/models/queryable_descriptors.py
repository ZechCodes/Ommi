from ommi import query_ast


class QueryableFieldDescriptor:
    def __init__(self, field, metadata):
        self.field = field
        self.metadata = metadata

    def __get__(self, instance, owner):
        if instance is None:
            return query_ast.ASTReferenceNode(self, owner)

        return self.field
