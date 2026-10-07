from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,62}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DesignRequest(StrictModel):
    text: str = Field(
        min_length=1,
        max_length=12000,
        pattern=r"\S",
        description="분석할 서비스 요청·장애 관리 요구사항 원문. 공백만 입력할 수 없습니다.",
    )


class Requirement(StrictModel):
    id: Annotated[str, Field(pattern=r"^C-REQ-[0-9]+$")]
    text: Text
    kind: Literal["functional", "nonfunctional"]
    provenance: Literal["source", "proposal"]
    evidence: list[Text]
    assumption: str
    needs_confirmation: bool
    needs_storage: bool


class Function(StrictModel):
    id: Annotated[str, Field(pattern=r"^C-FUN-[0-9]+$")]
    name: Text
    description: Text
    actor: Text
    inputs: list[Text]
    outputs: list[Text]
    preconditions: list[Text]
    rules: list[Text]
    exceptions: list[Text]
    priority: Literal["high", "medium", "low", "undecided"]


class ForeignKey(StrictModel):
    table: Identifier
    column: Identifier


class Column(StrictModel):
    name: Identifier
    type: Literal["integer", "bigint", "text", "boolean", "date", "timestamptz", "uuid"]
    nullable: bool
    primary_key: bool
    unique: bool
    references: ForeignKey | None


class Table(StrictModel):
    name: Identifier
    description: Text
    columns: list[Column] = Field(min_length=1)


class DataModel(StrictModel):
    tables: list[Table]


class Trace(StrictModel):
    requirement_id: Text
    function_ids: list[Text] = Field(min_length=1)
    tables: list[Identifier]
    reason: Text
    no_storage_reason: str


class Design(StrictModel):
    requirements: list[Requirement] = Field(min_length=1)
    functions: list[Function] = Field(min_length=1)
    data_model: DataModel
    traceability: list[Trace] = Field(min_length=1)
    assumptions: list[Text]
    questions: list[Text]


class Finding(StrictModel):
    kind: Literal["omission", "contradiction", "confirmation"]
    description: Text
    related_ids: list[Text]
    evidence: list[Text]
    suggestion: Text


class Review(StrictModel):
    findings: list[Finding]
    summary: Text


class ModelCall(StrictModel):
    stage: Literal["generate", "review"]
    model: str
    duration_ms: int
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


class Verification(StrictModel):
    structure: Literal["passed"] = "passed"
    semantic_review: Literal["completed"] = "completed"
    database_execution: Literal["not_run"] = "not_run"


class DesignResponse(StrictModel):
    status: Literal["completed_with_warnings"] = "completed_with_warnings"
    design: Design
    mermaid_erd: str
    postgresql_ddl: str
    review: Review
    verification: Verification = Field(default_factory=Verification)
    warnings: list[str]
    model_calls: list[ModelCall]
    prompt_caching_enabled: bool
    tracing_enabled: bool
