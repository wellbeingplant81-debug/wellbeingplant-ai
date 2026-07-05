from typing import List, Optional

from pydantic import BaseModel


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


class QualityReport(BaseModel):
    project_id: str
    technical_validation: TechnicalValidation
    ai_quality_evaluation: Optional[AIQualityEvaluation] = None
    metadata: QualityReportMetadata
