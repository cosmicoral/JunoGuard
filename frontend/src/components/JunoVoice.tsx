import { useEffect, useState } from "react";

/**
 * Juno's voice, via an ElevenLabs conversational agent.
 *
 * The widget is loaded lazily and only when an agent id is configured, so a
 * build without one ships no third-party script at all. The console must not
 * depend on this: if ElevenLabs is slow or blocked, nothing else on the page
 * changes.
 */

const AGENT_ID = import.meta.env.VITE_ELEVENLABS_AGENT_ID as string | undefined;
const WIDGET_SRC = "https://unpkg.com/@elevenlabs/convai-widget-embed";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "elevenlabs-convai": { "agent-id": string };
    }
  }
}

export function JunoVoice() {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!AGENT_ID) return;
    if (document.querySelector(`script[src="${WIDGET_SRC}"]`)) {
      setReady(true);
      return;
    }
    const script = document.createElement("script");
    script.src = WIDGET_SRC;
    script.async = true;
    script.type = "text/javascript";
    script.onload = () => setReady(true);
    script.onerror = () => setFailed(true);
    document.body.appendChild(script);
  }, []);

  if (!AGENT_ID || failed || !ready) return null;

  return (
    <div className="juno-voice" aria-label="Talk to Juno">
      <elevenlabs-convai agent-id={AGENT_ID} />
    </div>
  );
}
