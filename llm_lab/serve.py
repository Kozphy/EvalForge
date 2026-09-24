import argparse
import time
from fastapi import FastAPI
from pydantic import BaseModel

try:
    from vllm import LLM, SamplingParams
except Exception:
    LLM = None
    SamplingParams = None

app = FastAPI(title="EvalForge LLM Serving")
_engine = None


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 128
    temperature: float = 0.2


class GenerateResponse(BaseModel):
    text: str
    latency_ms: float


def configure(model: str, quantization: str | None = None):
    global _engine
    if LLM is None:
        raise RuntimeError("vLLM is not installed; install the serving extra on a CUDA/Linux host")
    _engine = LLM(model=model, quantization=quantization)


@app.get("/health")
def health():
    return {"ok": True, "engine_ready": _engine is not None}


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    if _engine is None:
        raise RuntimeError("engine not configured")
    params = SamplingParams(max_tokens=req.max_tokens, temperature=req.temperature)
    t0 = time.perf_counter()
    out = _engine.generate([req.prompt], params)[0].outputs[0].text
    latency = (time.perf_counter() - t0) * 1000
    return GenerateResponse(text=out, latency_ms=latency)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--quantization", default=None)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9000)
    args = p.parse_args()
    configure(args.model, args.quantization)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
