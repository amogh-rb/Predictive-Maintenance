import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, ApiError } from "../lib/api";
import PageHeader from "../components/PageHeader";
import { ChatIcon } from "../components/icons";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

interface CopilotResponse {
  reply: string;
}

// sessionStorage, not useState alone: this page unmounts every time the user
// switches to another sidebar tab (each route is a separate component in
// App.tsx), which would otherwise wipe the conversation. sessionStorage
// survives that and a page refresh, but not a new browser tab/session — no
// backend chat-history store, per the user's own scope: "not history of all
// chats, just per refresh or session".
const STORAGE_KEY = "fleetpulse.copilot.messages";

function loadMessages(): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

export default function CopilotPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(loadMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [notReady, setNotReady] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {
      // sessionStorage can throw (private browsing, quota) — losing history
      // on tab switch is a worse failure mode than a silently-skipped save.
    }
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const res = await api.post<CopilotResponse>("/v1/copilot/ask", { message: text });
      setMessages((prev) => [...prev, { role: "assistant", text: res.reply }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotReady(true);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: err instanceof ApiError ? err.detail : String(err) },
        ]);
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="copilot-page">
      <PageHeader icon={<ChatIcon />} title="Copilot" subtitle="Ask about fleet risk, a vehicle's health, or nearby depots." />
      {notReady && (
        <p className="problem-banner">
          The copilot isn't available right now. Please try again in a moment.
        </p>
      )}
      <div className="chat-log" ref={logRef}>
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>
            {/* Gemini's replies are markdown (lists, **bold**, `code`) — the
                user's own typed text never is, so only the assistant side is
                rendered through react-markdown; the user's text stays plain,
                which also avoids interpreting anything they type as markup. */}
            {m.role === "assistant" ? <ReactMarkdown>{m.text}</ReactMarkdown> : m.text}
          </div>
        ))}
      </div>
      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="e.g. which trucks at depot Chennai are highest risk?"
          disabled={sending}
        />
        <button onClick={send} disabled={sending || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
