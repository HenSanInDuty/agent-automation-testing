# Explicit live canary only. Never use this image for the offline test harness.
FROM auto-at-codex-bridge:0.164.0 AS bridge
FROM auto-at-codex-offline:playwright-1.50.1
USER root
COPY --from=bridge /usr/local/bin/codex /usr/local/bin/codex
COPY --from=bridge /usr/local/codex-resources /usr/local/codex-resources
COPY --from=bridge /app/codex-model-catalogue.json /app/codex-model-catalogue.json
COPY --from=bridge /app/codex-proposal-instructions.txt /app/codex-proposal-instructions.txt
COPY --from=bridge /app/apps/control-plane /app/apps/control-plane
COPY --from=bridge /app/packages/contracts /app/packages/contracts
RUN mkdir -p /bridge-home/.codex && chown -R pwuser:pwuser /bridge-home \
    && ln -s /usr/bin/python3 /usr/local/bin/python3 && rm /offline-evaluation
COPY benchmark/vision/codex/live_canary.py /app/benchmark/vision/codex/live_canary.py
ENV HOME=/bridge-home CODEX_HOME=/bridge-home/.codex
USER pwuser
ENTRYPOINT ["uv", "run", "--no-sync", "python", "benchmark/vision/codex/live_canary.py"]
