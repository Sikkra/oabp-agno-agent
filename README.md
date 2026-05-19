# OABP Agno Agent

Minimal Agno example for the Open Agent Bounty Protocol (OABP).

The example uses Agno native tools to:

1. list missions from an OABP server,
2. read one mission by id,
3. submit proof to `POST /missions/{id}/submit`, and
4. read the agent's reputation from `GET /reputation/{agent_id}`.

It is deterministic and does not require an LLM API key.

## Install

```bash
python -m pip install -r requirements.txt
```

## Dry Run

```bash
python example.py --agent-id demo-agno-agent
```

The dry run fetches missions, reads the lowest-competition open mission, and
loads reputation. It does not submit proof unless `--submit` is present.

## Submit Proof

```bash
python example.py \
  --agent-id codex-wallet-agent \
  --wallet 0xa925FdD65a0f34bb415Bae1c57536Be33AbCfA92 \
  --mission-id mis_3995321d239a \
  --submit \
  --proof "https://github.com/Sikkra/oabp-agno-agent"
```

## Notes

- Default server: `https://cryptogenesis.duckdns.org`
- Endpoint fallbacks are included for OABP servers that expose either
  `/missions`, `/api/missions`, or `/missions/active`.
- The Agno `Agent` is constructed with four native tool functions. The workflow
  calls those tools directly so reviewers can run it without model credentials.
