import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Download, ExternalLink, Globe, Puzzle, Shield } from "lucide-react";

type Step = "extension" | "done";

interface ExtensionStatus {
  detected: boolean;
  checking: boolean;
}

const EXTENSION_STORE_URL =
  "https://chrome.google.com/webstore/detail/isitme";

function useExtensionDetection(): ExtensionStatus {
  const [detected, setDetected] = useState(false);
  const [checking, setChecking] = useState(true);

  const probe = useCallback(() => {
    if (typeof chrome === "undefined" || !chrome?.runtime?.sendMessage) {
      setDetected(false);
      setChecking(false);
      return;
    }
    try {
      chrome.runtime.sendMessage(
        { kind: "getStatus" },
        (response: unknown) => {
          if (chrome.runtime.lastError || !response) {
            setDetected(false);
          } else {
            setDetected(true);
          }
          setChecking(false);
        },
      );
    } catch {
      setDetected(false);
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    probe();
    const interval = setInterval(probe, 3000);
    return () => clearInterval(interval);
  }, [probe]);

  return { detected, checking };
}

export function SetupWizard({ onDismiss }: { onDismiss: () => void }) {
  const [step, setStep] = useState<Step>("extension");
  const ext = useExtensionDetection();

  useEffect(() => {
    if (ext.detected && step === "extension") {
      setStep("done");
    }
  }, [ext.detected, step]);

  return (
    <div className="card mx-auto max-w-xl p-6 sm:p-8">
      <div className="text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-accent/10">
          <Puzzle className="h-6 w-6 text-accent" />
        </div>
        <h2 className="mt-4 text-xl font-semibold text-neutral-100">
          Set up your brain
        </h2>
        <p className="mt-2 text-sm text-neutral-400">
          Install the browser extension so isitme can capture your activity and
          build your knowledge graph.
        </p>
      </div>

      {step === "extension" && (
        <div className="mt-8 space-y-4">
          <div className="flex items-start gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
            <Globe className="mt-0.5 h-5 w-5 shrink-0 text-accent-soft" />
            <div className="flex-1">
              <h3 className="text-sm font-medium text-neutral-100">
                Install the isitme extension
              </h3>
              <p className="mt-1 text-xs text-neutral-500 leading-relaxed">
                The extension captures visits, searches, clicks, dwell time, and
                optionally LLM prompts — all with client-side redaction.
              </p>

              {ext.checking ? (
                <div className="mt-3 flex items-center gap-2 text-xs text-neutral-500">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-accent/60" />
                  Checking for extension…
                </div>
              ) : ext.detected ? (
                <div className="mt-3 flex items-center gap-2 text-xs text-emerald-400/80">
                  <CheckCircle2 className="h-4 w-4" />
                  Extension detected — you're all set!
                </div>
              ) : (
                <div className="mt-4 space-y-3">
                  <div className="rounded-lg border border-white/[0.06] bg-ink-950 p-3">
                    <p className="eyebrow mb-2">Option 1 — Load unpacked (dev)</p>
                    <ol className="list-inside list-decimal space-y-1 text-xs text-neutral-400">
                      <li>
                        Build:{" "}
                        <code className="text-neutral-300">
                          cd packages/browser-extension && npm run build
                        </code>
                      </li>
                      <li>
                        Open{" "}
                        <code className="text-neutral-300">
                          chrome://extensions
                        </code>{" "}
                        → Developer mode
                      </li>
                      <li>
                        <strong className="text-neutral-300">Load unpacked</strong>{" "}
                        → select{" "}
                        <code className="text-neutral-300">dist/</code>
                      </li>
                    </ol>
                  </div>
                  <a
                    href={EXTENSION_STORE_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-ghost flex w-full items-center justify-center gap-2 !rounded-lg !py-2 text-xs"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Chrome Web Store
                    <ExternalLink className="h-3 w-3 opacity-40" />
                  </a>
                  <p className="text-center text-[11px] text-neutral-600">
                    After installing, this screen will auto-detect the extension.
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-start gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
            <Shield className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400/60" />
            <div>
              <h3 className="text-sm font-medium text-neutral-100">
                No API key needed
              </h3>
              <p className="mt-1 text-xs text-neutral-500 leading-relaxed">
                The extension authenticates with Google (the same account you just
                signed in with). Your data is captured locally and sent only to
                your brain server.
              </p>
            </div>
          </div>

          {ext.detected ? (
            <button
              onClick={() => setStep("done")}
              className="btn-primary mt-2 w-full !rounded-xl"
            >
              Continue
            </button>
          ) : (
            <button
              onClick={onDismiss}
              className="btn-ghost mt-2 w-full !rounded-xl text-xs"
            >
              Skip for now — I'll install it later
            </button>
          )}
        </div>
      )}

      {step === "done" && (
        <div className="mt-8 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/10">
            <CheckCircle2 className="h-7 w-7 text-emerald-400" />
          </div>
          <h3 className="mt-4 text-lg font-medium text-neutral-100">
            You're all set!
          </h3>
          <p className="mt-2 text-sm text-neutral-400">
            Your brain is capturing. Browse the web normally and watch your
            knowledge graph grow in real time.
          </p>
          <button
            onClick={onDismiss}
            className="btn-primary mt-6 !rounded-xl"
          >
            Open dashboard
          </button>
        </div>
      )}
    </div>
  );
}
