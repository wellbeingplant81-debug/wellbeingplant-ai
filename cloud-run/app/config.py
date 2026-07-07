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
