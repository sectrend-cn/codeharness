"""Java null and primitive literal guarded field assignments."""

from code_harness.languages.projection_syntax import GrammarProjection


class JavaProjection(GrammarProjection):
    """Match direct fields; accessor methods and collection put calls are operations."""

    regions = frozenset({"block", "constructor_body"})
    blocks = frozenset({"block", "constructor_body"})
    nulls = frozenset({"null_literal"})
    strings = frozenset({"string_literal", "character_literal"})
    numbers = frozenset(
        {
            "decimal_integer_literal",
            "hex_integer_literal",
            "octal_integer_literal",
            "binary_integer_literal",
            "decimal_floating_point_literal",
            "hex_floating_point_literal",
        }
    )
