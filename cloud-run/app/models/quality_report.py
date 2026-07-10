from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RequiredFilesCheck(BaseModel):
    passed: bool
    missing: List[str]


class SceneCountCheck(BaseModel):
    passed: bool
    script_scenes: int
    image_files: int
    audio_files: int


class ImageResolutionDetail(BaseModel):
    label: str
    width: int
    height: int
    portrait: bool


class ImageResolutionCheck(BaseModel):
    passed: bool
    warnings: List[str]
    details: List[ImageResolutionDetail]


class VideoDurationCheck(BaseModel):
    passed: bool
    duration_seconds: Optional[float] = None


class SubtitleExistenceCheck(BaseModel):
    passed: bool
    cue_count: int


class AudioVideoSyncCheck(BaseModel):
    passed: bool
    video_duration_seconds: Optional[float] = None
    audio_duration_seconds: Optional[float] = None
    delta_ms: Optional[float] = None
    tolerance_ms: float


class ThumbnailExistenceCheck(BaseModel):
    passed: bool


class TechnicalChecks(BaseModel):
    required_files_exist: RequiredFilesCheck
    scene_count_consistency: SceneCountCheck
    image_resolution: ImageResolutionCheck
    video_duration: VideoDurationCheck
    subtitle_existence: SubtitleExistenceCheck
    audio_video_sync: AudioVideoSyncCheck
    thumbnail_existence: ThumbnailExistenceCheck


class PerformanceMetrics(BaseModel):
    project_creation_seconds: float
    script_generation_seconds: float
    image_generation_seconds: float
    tts_generation_seconds: float
    subtitle_generation_seconds: float
    video_rendering_seconds: float
    thumbnail_generation_seconds: float
    quality_evaluation_seconds: float
    total_generation_time_seconds: float
    final_file_size_bytes: int
    thumbnail_file_size_bytes: int


class TechnicalValidation(BaseModel):
    passed: bool
    checks: TechnicalChecks
    performance_metrics: PerformanceMetrics
    blocking_failures: List[str]


class QualityScores(BaseModel):
    hook_strength: int
    scene1_quality: int
    thumbnail_quality: int
    image_realism: int
    character_consistency: int
    composition: int
    overall_quality: int


class SceneQuality(BaseModel):
    scene: int
    realism_score: int
    composition_score: int
    regenerate: bool
    reason: Optional[str] = None


class ThumbnailQuality(BaseModel):
    consistency_with_scene1: int
    ctr_score: int
    regenerate: bool
    reason: Optional[str] = None


class QualitySummary(BaseModel):
    regenerate_recommended: bool
    scenes_to_regenerate: List[int]
    notes: str


class AIQualityEvaluation(BaseModel):
    scores: QualityScores
    scenes: List[SceneQuality]
    thumbnail: ThumbnailQuality
    summary: QualitySummary


class QualityReportMetadata(BaseModel):
    evaluated_at: str
    schema_version: str
    ai_evaluation_skipped_reason: Optional[str] = None


class RetryAttempt(BaseModel):
    attempt: int
    outcome: str  # "success" | "error"
    reason: Optional[str] = None
    timestamp: str


class RegenerationState(BaseModel):
    retry_count: int = 0
    retry_history: List[RetryAttempt] = Field(default_factory=list)
    final_status: Optional[str] = None  # "passed" | "failed_max_retry"


class SceneRegenerationEntry(BaseModel):
    scene: int
    regeneration: RegenerationState = Field(default_factory=RegenerationState)


class VisualDiversitySummary(BaseModel):
    """Sprint72-3 - Visual Diversity QA. visual_diversity_engine.
    summarize_visual_diversity()의 결과 + scene별 profile을 그대로
    담는다. 새 판정 로직은 없다 - 기존 함수 결과를 직렬화할 뿐이다."""

    camera_distance_distribution: Dict[str, int] = Field(default_factory=dict)
    camera_angle_distribution: Dict[str, int] = Field(default_factory=dict)
    composition_distribution: Dict[str, int] = Field(default_factory=dict)
    lighting_distribution: Dict[str, int] = Field(default_factory=dict)
    camera_distance_diversity_count: int = 0
    camera_angle_diversity_count: int = 0
    composition_diversity_count: int = 0
    lighting_diversity_count: int = 0
    diversity_score: float = 0.0
    profiles_by_scene: Dict[int, Dict[str, str]] = Field(default_factory=dict)


class SubpromptDiagnosticsSummary(BaseModel):
    """Sprint73 - Subprompt Quality Gate Observability. scene별
    subprompt_service 진단 정보(폴백 발생 여부/이유/원본 예외 메시지/
    당시 image_prompt 길이)를 모은다. fallback_reason은 Gemini 응답
    자체의 문제(count_mismatch/duplicate_subprompts/
    near_duplicate_keywords/missing_dimension)와 예외성 오류
    (generation_error)를 구분하고, prompt_length는 scene마다 함께
    기록해 "Prompt 길이 증가가 원인인지" 교차 확인할 수 있게 한다."""

    scenes_with_fallback: List[int] = Field(default_factory=list)
    fallback_reasons_by_scene: Dict[int, str] = Field(default_factory=dict)
    fallback_details_by_scene: Dict[int, str] = Field(default_factory=dict)
    prompt_lengths_by_scene: Dict[int, int] = Field(default_factory=dict)


class QualityReport(BaseModel):
    project_id: str
    technical_validation: TechnicalValidation
    ai_quality_evaluation: Optional[AIQualityEvaluation] = None
    regeneration: List[SceneRegenerationEntry] = Field(default_factory=list)
    metadata: QualityReportMetadata
    # Sprint72-3 - visual_profile이 있는 scene이 하나도 없으면(요구
    # 사항: profile=None이면 완전 no-op) None으로 남아 기존
    # quality_report.json 스키마와 완전히 하위 호환된다.
    visual_diversity: Optional[VisualDiversitySummary] = None
    # Sprint73 - subprompt_diagnostics가 있는 scene이 하나도 없으면
    # None으로 남아 기존 스키마와 완전히 하위 호환된다.
    subprompt_diagnostics: Optional[SubpromptDiagnosticsSummary] = None
