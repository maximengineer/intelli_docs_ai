# AWS Deployment Notes

These are production-inspired deployment notes, not a claim that IntelliDocs AI
is enterprise-ready.

## Minimal Shape

- Backend: ECS Fargate service running the FastAPI container.
- Worker: separate ECS Fargate service running the Celery worker command.
- Broker: Amazon ElastiCache for Redis.
- Database: Amazon RDS PostgreSQL with the `vector` extension enabled where
  available, or a managed Postgres provider that supports pgvector.
- Frontend: Streamlit container behind an internal or public load balancer.

## Required Configuration

- `DATABASE_URL`
- `VECTOR_STORE_BACKEND=postgres`
- `EMBEDDING_BACKEND=hash` for the no-key demo, or a real embedding backend with
  a matching `POSTGRES_VECTOR_DIMENSION`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `ENABLE_LLM` and provider keys only when running live LLM calls

## Operational Notes

- Run Alembic migrations before accepting traffic.
- Keep raw document text out of logs.
- Set upload size limits at the load balancer and application layers.
- Store secrets in AWS Secrets Manager or SSM Parameter Store.
- For self-managed Redis on a VPS, set `vm.overcommit_memory=1` persistently
  (for example in `/etc/sysctl.d/99-intellidocs-redis.conf`) before using Redis
  as the Celery broker. Managed services such as ElastiCache handle host kernel
  configuration outside the application stack.
- Treat cost estimates as application logs, not billing-grade accounting.
  `token_usage_source=provider` means provider usage metadata was available;
  `token_usage_source=estimate` means the app used a local word-count estimate.
  Offline/local heuristic runs report API cost as `$0.00`; local compute cost is
  not estimated. Provider calls report `estimated_cost_usd=null` and
  `cost_estimate_available=false` when token prices have not been configured;
  zero must not be interpreted as a free paid-provider call.
