import { useState } from "react";
import { api } from "../lib/api";
import type { AskResponse } from "../lib/types";

export function AskBox() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.ask(question.trim());
      setAnswer(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-neutral-100">Ask your brain</h3>
        {answer && (
          <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-neutral-400">
            {answer.synthesized_by === "openai" ? "synthesized by OpenAI" : "templated"}
          </span>
        )}
      </div>
      <form onSubmit={submit} className="mt-4">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What have I been researching about vector databases?"
          rows={3}
          className="w-full resize-none rounded-xl border border-white/[0.08] bg-ink-950 px-4 py-3 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-accent/50 focus:outline-none"
        />
        <div className="mt-3 flex justify-end">
          <button type="submit" disabled={loading || !question.trim()} className="btn-primary">
            {loading ? "Thinking…" : "Ask"}
          </button>
        </div>
      </form>

      {error && <p className="mt-3 text-sm text-rose-400/80">{error}</p>}

      {answer && (
        <div className="mt-4 space-y-4">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-neutral-300">
            {answer.answer}
          </p>
          {answer.sources.length > 0 && (
            <div>
              <div className="eyebrow mb-2">Sources</div>
              <div className="space-y-2">
                {answer.sources.slice(0, 5).map((s) => (
                  <div
                    key={s.id}
                    className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs text-neutral-400"
                  >
                    <span className="mr-2 font-mono text-[10px] text-neutral-600 tnum">
                      {s.score.toFixed(2)}
                    </span>
                    {s.text.slice(0, 180)}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
