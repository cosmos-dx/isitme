import { useState } from "react";
import Markdown from "react-markdown";
import { Loader2 } from "lucide-react";
import { api } from "../lib/api";
import type { AskResponse } from "../lib/types";

export function AskBox() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const doAsk = async () => {
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void doAsk();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void doAsk();
    }
  };

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-neutral-100">
          Ask your brain
        </h3>
        {answer && (
          <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-neutral-400">
            {answer.synthesized_by === "openai"
              ? "synthesized by OpenAI"
              : "templated"}
          </span>
        )}
      </div>

      <form onSubmit={handleSubmit} className="mt-4">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What have I been researching about vector databases?"
          rows={3}
          className="w-full resize-none rounded-xl border border-white/[0.08] bg-ink-950 px-4 py-3 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-accent/50 focus:outline-none"
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[10px] text-neutral-600">
            Enter to send · Shift+Enter for newline
          </span>
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="btn-primary"
          >
            {loading ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Thinking…
              </>
            ) : (
              "Ask"
            )}
          </button>
        </div>
      </form>

      {error && <p className="mt-3 text-sm text-rose-400/80">{error}</p>}

      {loading && !answer && (
        <div className="mt-4 flex items-center gap-2 text-sm text-neutral-500">
          <Loader2 size={16} className="animate-spin text-accent" />
          <span>Searching your memories…</span>
        </div>
      )}

      {answer && (
        <div className="mt-4 space-y-4">
          <div className="md-body text-sm leading-relaxed text-neutral-300">
            <Markdown>{answer.answer}</Markdown>
          </div>

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

          {answer.graph_context.length > 0 && (
            <div>
              <div className="eyebrow mb-2">Graph context</div>
              <div className="flex flex-wrap gap-2">
                {answer.graph_context.slice(0, 6).map((gc) => (
                  <span
                    key={gc.topic}
                    className="rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-xs text-neutral-300"
                  >
                    {gc.topic}
                    <span className="ml-1 font-mono text-[10px] text-neutral-500 tnum">
                      {gc.weight.toFixed(1)}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
