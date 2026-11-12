using System.Globalization;
using System.Text.Json.Nodes;

namespace Orbit.Api;

public static class Validation
{
    public static List<string> Value(
        JsonNode? value,
        JsonObject property,
        string unit,
        bool required,
        bool interpret
    )
    {
        var errors = new List<string>();
        if (
            value == null
            || value is JsonValue v
                && v.TryGetValue<string>(out var blank)
                && string.IsNullOrWhiteSpace(blank)
            || value is JsonArray list && list.Count == 0
        )
        {
            if (required)
                errors.Add("Required value is missing.");
            return errors;
        }
        var units = new HashSet<string>(StringComparer.Ordinal);
        if (property.S("unit").Length > 0)
            units.Add(property.S("unit"));
        foreach (var u in property["units"]?.AsArray() ?? new JsonArray())
            if (u != null)
                units.Add(u is JsonObject ? u.S("symbol", u.S("name")) : u.ToString());
        if (units.Count > 0 && !units.Contains(unit) || units.Count == 0 && unit.Length > 0)
            errors.Add("Choose a unit returned by the selected property definition.");
        var values = value is JsonArray array ? array.ToList() : [value];
        foreach (var original in values)
        {
            var typed = original;
            if (
                interpret
                && typed is JsonValue textValue
                && textValue.TryGetValue<string>(out var text)
                && property.S("dataType") != "String"
            )
            {
                try
                {
                    typed = JsonNode.Parse(text);
                }
                catch (System.Text.Json.JsonException)
                {
                    errors.Add("Native text cannot be interpreted as the selected property type.");
                    continue;
                }
            }
            var isString = typed is JsonValue scalar && scalar.TryGetValue<string>(out _);
            var raw = typed?.ToJsonString() ?? "null";
            var good = property.S("dataType") switch
            {
                "String" => isString,
                "Boolean" => raw is "true" or "false",
                "Integer" => !isString
                    && long.TryParse(
                        raw,
                        NumberStyles.Integer,
                        CultureInfo.InvariantCulture,
                        out _
                    ),
                "Real" or "Number" => !isString
                    && decimal.TryParse(
                        raw,
                        NumberStyles.Float,
                        CultureInfo.InvariantCulture,
                        out _
                    ),
                _ => false,
            };
            if (!good)
                errors.Add("Value does not match the selected bSDD data type.");
            var allowed = property["allowedValues"]?.AsArray();
            if (
                allowed?.Count > 0
                && !allowed.Any(a => JsonNode.DeepEquals(a is JsonObject ? a["value"] : a, typed))
            )
                errors.Add("Value is not in the selected property's allowed values.");
        }
        return errors.Distinct().ToList();
    }

    public static JsonObject Property(JsonObject? reference, string uri)
    {
        if (reference == null || !reference.B("enabled"))
            throw new ApiException(
                409,
                "Enable the project bSDD reference before using property validation."
            );
        return reference["properties"]
            ?.AsArray()
            .SingleOrDefault(p => p.S("uri") == uri)
            ?.AsObject()
            ?? throw new ApiException(409, "The selected bSDD property is no longer available.");
    }
}
