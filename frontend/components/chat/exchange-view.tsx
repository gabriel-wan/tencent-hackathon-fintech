import { AnswerCard } from "./answer-card";
import type { Exchange } from "./types";

type Props = { exchange: Exchange; onRetry: () => void; retryDisabled: boolean };

// One question and its answer.
export function ExchangeView({ exchange, onRetry, retryDisabled }: Props) {
  return (
    <li className="grid gap-3">
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 leading-relaxed whitespace-pre-wrap">
        <span className="sr-only">You asked: </span>
        {exchange.question}
      </div>
      <AnswerCard exchange={exchange} onRetry={onRetry} retryDisabled={retryDisabled} />
    </li>
  );
}
