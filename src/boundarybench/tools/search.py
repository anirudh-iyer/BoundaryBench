"""The only model-callable tool accepts a query, never authenticated attributes."""

import json

from pydantic import Field

from boundarybench.models.llm import FrozenModel, ToolDefinition


class SearchArguments(FrozenModel):
    query: str = Field(min_length=1)


SEARCH_TOOL = ToolDefinition(
    name="search",
    description="Search course documents using topic words.",
    parameters_json=json.dumps(SearchArguments.model_json_schema(), sort_keys=True),
)
