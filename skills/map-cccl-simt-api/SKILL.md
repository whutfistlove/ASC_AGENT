---
name: map-cccl-simt-api
description: Audit external CUDA APIs referenced by CCCL libcudacxx headers and map them to locally documented Ascend SIMT APIs. Use for per-file dependency API extraction, CUDA-to-Ascend semantic matching, and evidence-backed mapping reports against docs/SIMT-API.
---

# Map CCCL APIs to Ascend SIMT APIs

Work in two explicit stages. Return one JSON object only and follow the schema supplied by the caller.

## Extract source APIs

Read the complete numbered source shard. Treat deterministic candidates as an audit checklist, not as the API list.

- Find every external public CUDA/NV device-side platform API referenced by this file that may need an Ascend SIMT counterpart. Include global CUDA intrinsics/functions and device-callable data types used by the implementation. Examples include `::__brev`, `::__brevll`, `::sincosf`, `::__half`, and `::__half2float`. Always set `origin` to `referenced`.
- Do not output APIs rooted at `cuda::` or `cuda::std::` (for example `::cuda::neg`, `::cuda::std::forward`, `::cuda::std::sin`, type traits, aliases, and other libcudacxx utilities). They are package-internal dependencies that will migrate through the dependency closure, not external SIMT replacement targets. Classify their candidates as `non_api`.
- Do not output public APIs declared or defined by the file being analyzed. They are the interfaces being implemented, not external dependencies to replace. Classify their declaration candidates as `non_api` for this mapping task.
- Include device-callable functions, host/device functions, external public host-only CUDA runtime/driver functions, device data types, and compile-time entities usable by device code. Set `device_support` to `host_only` for host-only functions; they remain API records and mapping targets.
- Exclude CUDA runtime/driver types named `cuda*` or `CU*`—handles, configuration/query types, structs, and enum types—even if source annotations or model inference label them `host_device`. This exclusion does not apply to device-callable data types such as `__half`, `__nv_bfloat16`, and FP8 types.
- Exclude ordinary constants and enum members. Keep CUDA device built-in variables such as `threadIdx`, `blockIdx`, `blockDim`, `gridDim`, and `warpSize` in scope.
- Output only public APIs and set their `visibility` to `public`. Internal helpers and implementation declarations must be classified as `non_api` in candidate coverage and must not appear in `apis`.
- Exclude all preprocessor macros for now, including header guards, feature switches, attributes, dispatch wrappers, and function-like macros. Macro definitions are source context only and are not API candidates or API records.
- A leading underscore is evidence of an internal helper but is not conclusive: documented CUDA intrinsics such as `__brev` can still be public APIs. Use namespace, comments, aggregation headers, and calling intent to decide.
- Do not count control flow, language casts, comments, string literals, include-only re-exports, macro invocations, internal helpers declared by this file, or calls to those internal helpers. Ordinary invocations are API records only when the callee is an external public CUDA API.
- Deduplicate repeated references to the same qualified external API within the file. Record one API row and preserve a representative observed call/use form.
- Use exact qualified names when recoverable.
- Cite source line ranges and concise source evidence. Never invent a declaration hidden behind an unresolved macro; classify it as uncertain and explain why.
- Account for every supplied candidate ID in `coverage`, even when it is a false positive, duplicate, invocation, or excluded runtime/driver type. APIs missed by the candidate scanner must still be added with an empty `candidate_ids` list.

## Map to local documentation

Read every supplied source API and its retrieved documentation candidates.

- Compare semantics, inputs/outputs, type support, execution scope, synchronization/memory behavior, and edge cases. Similar names alone are insufficient.
- Cite only documentation candidates supplied in the request. A cited path must contain the named Ascend API.
- Use `exact` only when signatures, supported types, execution scope, outputs, and edge behavior are substitutable. Use `partial` whenever either side supports a narrower type/range/scope. Use `semantic` for a composition or conceptually corresponding API, `uncertain` for insufficient evidence, and `no_match` when none of the supplied documents supports a mapping.
- Cite only documents listed for that specific source API in `RETRIEVAL_BY_API_JSON`; documents retrieved for another API in the same batch are not evidence for this API.
- For `no_match`, return empty `accl_apis`, `doc_paths`, and `doc_evidence`. Do not guess.
- Keep evidence short and grounded in the supplied document text. Explain material differences in `mapping_notes`.
- Return exactly one mapping record for every source API ID supplied by the caller.
