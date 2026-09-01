local sensitive = { authorization=true, cookie=true, token=true, secret=true, password=true, api_key=true }

function redact(tag, timestamp, record)
    -- Only first-party JSON envelopes proceed to Loki. Docker, browser, and
    -- third-party records cannot create fallback labels or leak raw output.
    if type(record["service"]) ~= "string"
        or type(record["environment"]) ~= "string"
        or type(record["level"]) ~= "string" then
        return -1, timestamp, record
    end
    for key, value in pairs(record) do
        local normalized = string.lower(key)
        if sensitive[normalized] or string.find(normalized, "token") or string.find(normalized, "secret") or string.find(normalized, "password") then
            record[key] = "[REDACTED]"
        elseif type(value) == "string" then
            value = string.gsub(value, "[Bb]earer%s+[%w%._%-]+", "Bearer [REDACTED]")
            record[key] = value
        end
    end
    return 1, timestamp, record
end
