"""Read every model-facing tool declaration in a synthetic captured request."""


def declared_tool_names(request: dict) -> list[str]:
    names = []

    def collect(tools, prefix=""):
        if not isinstance(tools, list):
            raise ValueError("malformed tool declarations")
        for tool in tools:
            if not isinstance(tool, dict):
                raise ValueError("malformed tool declaration")
            name = tool.get("name", tool.get("type"))
            if not isinstance(name, str) or not name:
                raise ValueError("unnamed tool declaration")
            if tool.get("type") == "namespace":
                collect(tool.get("tools"), prefix + name + ".")
            else:
                names.append(prefix + name)

    collect(request.get("tools", []))
    for item in request.get("input", []):
        if isinstance(item, dict) and item.get("type") == "additional_tools":
            collect(item.get("tools"))
    return names
