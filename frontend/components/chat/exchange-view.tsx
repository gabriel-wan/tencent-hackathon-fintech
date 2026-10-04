import type { Exchange } from "./types";

// One question and its answer.
export function ExchangeView({ exchange }: { exchange: Exchange }) {
  return (
    <li className="grid gap-3">
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 whitespace-pre-wrap">
        <span className="sr-only">You asked: </span>
        {exchange.question}
      </div>
      <div aria-busy={exchange.status === "pending"}>
        {exchange.status === "pending"
          ? "Searching your sources…"
          : exchange.status === "failed"
            ? `Failed: ${exchange.failure}`
            : exchange.response.answer}
      </div>
    </li>
  );
}
