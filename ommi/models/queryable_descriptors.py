"""
Descriptor for Queryable Fields in Ommi Models

This module defines a descriptor that enables fields within Ommi models to be
queried through the AST (Abstract Syntax Tree) system. The QueryableFieldDescriptor
allows for seamless interaction with the Ommi query system by returning an
ASTReferenceNode when accessed from the class level, and the actual field when
accessed from an instance.
"""


from ommi import query_ast


class QueryableFieldDescriptor:
    def __init__(self, field, metadata):
        self.field = field
        self.metadata = metadata

    def __get__(self, instance, owner):
        if instance is None:
            return query_ast.ASTReferenceNode(self, owner)

        return self.field
