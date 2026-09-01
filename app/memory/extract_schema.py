"""Structured extraction schema for Vertex/Gemini propose()."""

MEMORY_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "patches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "text": {"type": "string"},
                    "workstream_id": {"type": "string"},
                    "referent_id": {"type": "string", "nullable": True},
                    "slot": {"type": "string", "nullable": True},
                    "action": {"type": "string"},
                    "supersedes_id": {"type": "string", "nullable": True},
                    "uncertain": {"type": "boolean"},
                },
                "required": ["kind", "text", "workstream_id"],
            },
        },
        "abstain": {"type": "boolean"},
    },
    "required": ["patches"],
}
