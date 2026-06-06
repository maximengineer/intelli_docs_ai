# IntelliDocs AI Demo Script

1. Start the backend and Streamlit UI.
2. (Optional) Set `ENABLE_LLM=true` and `OPENROUTER_API_KEY` in `.env` to demo the real LLM path; otherwise the deterministic offline fallback runs.
3. Upload `data/sample_documents/invoice_acme.txt`.
4. Confirm that IntelliDocs AI extracts the vendor, amount, currency and dates.
5. Upload `data/sample_documents/contract_northwind.txt`.
6. Ask: `Which invoice is above 10,000 EUR?`
7. Show that the answer includes backend-mapped source metadata.
8. Ask: `What is the largest operational risk for Q2?`
9. Ask: `Which document mentions a Singapore office?`
10. Show the insufficient-information fallback.
11. Run `uv run python scripts/run_evaluation.py`.
12. Point out the honest `unsupported_answer_rejection_rate` of 0.8 on the offline backend, and explain why (the lexical fallback is fooled by a keyword-dense but unanswerable question).
13. Explain that Phase 1 uses local deterministic components by default and an OpenRouter provider when configured, while Phase 2 adds async processing and pgvector.
