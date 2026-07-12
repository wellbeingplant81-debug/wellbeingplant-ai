QUALITY_MAX_RETRY = 3

# Sprint45 - Scene Planner Integration Engine. Off by default: the
# pipeline's default behavior/output (script.json shape included) must
# stay byte-for-byte identical unless this is explicitly turned on.
ENABLE_SCENE_PLANNER = False

# Sprint46 - Prompt Enrichment Engine. Off by default. Only takes effect
# when ENABLE_SCENE_PLANNER also produced a scene_plan - if Planner is
# disabled (or failed), image_prompt stays byte-for-byte identical
# regardless of this flag.
ENABLE_PROMPT_ENRICHMENT = False

# Sprint47 - Prompt Effectiveness Engine. Off by default. Measurement
# only - never changes data["scenes"] or any generation output, so
# leaving this False (or True) never affects the pipeline's rendered
# result, only whether project_data["prompt_metrics"] is populated.
ENABLE_PROMPT_EFFECTIVENESS = False

# Sprint48 - Adaptive Prompt Optimization Engine. Off by default. Only
# takes effect when ENABLE_PROMPT_EFFECTIVENESS also produced
# prompt_metrics - if Effectiveness is disabled (or failed), image_prompt
# stays byte-for-byte identical regardless of this flag.
ENABLE_PROMPT_OPTIMIZATION = False

# Sprint49 - Self-Learning Prompt Engine. Off by default. In-memory only
# (no file I/O, no DB, no external calls) - never adds keys to
# project_data and never changes data["scenes"], so this flag cannot
# affect the pipeline's output either way. Only takes effect when
# ENABLE_PROMPT_EFFECTIVENESS also produced prompt_metrics to learn from.
ENABLE_PROMPT_LEARNING = False

# Sprint50 - AI Director v1. Off by default. Pure rule-based read-only
# decision engine - never modifies data["scenes"] or any other pipeline
# output, only ever adds data["director_decision"] when enabled.
ENABLE_AI_DIRECTOR = False

# Sprint51 Phase 1 - Viral Writer Engine. Off by default. Only swaps which
# prompt template script_service.generate_script() sends to Gemini - the
# output JSON shape (title/hook/script/scenes[scene,narration,image_prompt])
# is unchanged either way, so every downstream module (Sprint44-50) keeps
# working without modification. Flag off means byte-for-byte identical
# behavior to pre-Sprint51.
ENABLE_VIRAL_WRITER = False

# Sprint77 - Asset Planner v1. Off by default. asset_planner.plan_asset_
# strategy() only unifies two existing batch-level computations
# (select_ai_priority_scenes/assign_visual_profiles) that step02_assets.
# collect_assets() already runs inline - when this flag is off,
# collect_assets() falls back to that exact same inline computation
# (asset_plan=None), so pipeline output is byte-for-byte identical to
# pre-Sprint77 regardless of this flag's value today. Turning it on only
# adds data["asset_plan"] for observability/future extension; it does not
# change today's asset selection outcome.
ENABLE_ASSET_PLANNER = False

# Sprint93 - ProductionProfile Activation. Off by default. When off,
# pipeline.run_pipeline() never calls ProductionProfileIntegration and
# never adds data["production_profile"] - output is byte-for-byte
# identical to pre-Sprint93. When on, it stores
# ProductionProfileIntegration.load_profile(enabled=True) under
# data["production_profile"] for observability; nothing downstream reads
# it yet.
ENABLE_PRODUCTION_PROFILE = False
