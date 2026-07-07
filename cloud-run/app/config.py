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
