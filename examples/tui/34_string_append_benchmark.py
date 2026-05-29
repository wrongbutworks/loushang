from __future__ import annotations

from dataclasses import dataclass
import argparse
from io import StringIO
import random
from time import perf_counter


@dataclass(frozen=True, slots=True)
class DraftRecord:
    text: str


def benchmark_plus_equal(*, chunks: tuple[str, ...], repeat: int) -> tuple[float, int]:
    started = perf_counter()
    size = 0
    for _ in range(repeat):
        text = ""
        for chunk in chunks:
            text += chunk
        size += len(text)
    return (perf_counter() - started) * 1000, size


def benchmark_plus_equal_aliased(*, chunks: tuple[str, ...], repeat: int) -> tuple[float, int]:
    started = perf_counter()
    size = 0
    for _ in range(repeat):
        text = ""
        aliases: list[str] = []
        for chunk in chunks:
            aliases.append(text)
            text += chunk
        size += len(text)
    return (perf_counter() - started) * 1000, size


def benchmark_record_rebuild(*, chunks: tuple[str, ...], repeat: int) -> tuple[float, int]:
    started = perf_counter()
    size = 0
    for _ in range(repeat):
        record: DraftRecord | None = None
        for chunk in chunks:
            if record is None:
                record = DraftRecord(chunk)
            else:
                record = DraftRecord(record.text + chunk)
        size += len(record.text) if record is not None else 0
    return (perf_counter() - started) * 1000, size


def benchmark_list_join(*, chunks: tuple[str, ...], repeat: int) -> tuple[float, int]:
    started = perf_counter()
    size = 0
    for _ in range(repeat):
        parts: list[str] = []
        for chunk in chunks:
            parts.append(chunk)
        text = "".join(parts)
        size += len(text)
    return (perf_counter() - started) * 1000, size


def benchmark_string_io(*, chunks: tuple[str, ...], repeat: int) -> tuple[float, int]:
    started = perf_counter()
    size = 0
    for _ in range(repeat):
        buffer = StringIO()
        for chunk in chunks:
            buffer.write(chunk)
        text = buffer.getvalue()
        size += len(text)
    return (perf_counter() - started) * 1000, size


def make_chunks(
    *,
    count: int,
    line_width: int,
    random_lengths: bool,
    min_line_width: int,
    max_line_width: int,
    seed: int,
) -> tuple[str, ...]:
    rng = random.Random(seed)
    chunks: list[str] = []
    for index in range(1, count + 1):
        width = rng.randint(min_line_width, max_line_width) if random_lengths else line_width
        chunks.append(_make_line_chunk(index=index, line_width=width))
    return tuple(chunks)


def _make_line_chunk(*, index: int, line_width: int) -> str:
    prefix = f"- Line {index}: markdown code-{index} "
    suffix = f" with 中文宽字符 and link {index} (https://example.com/{index}).\n"
    filler_width = max(0, line_width - len(prefix) - len(suffix))
    return f"{prefix}{'x' * filler_width}{suffix}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Python string append strategies for streaming chunks.")
    parser.add_argument("--chunks", type=int, default=5_000, help="number of chunks to append")
    parser.add_argument("--line-width", type=int, default=96, help="approximate line width per chunk")
    parser.add_argument("--random-lengths", action="store_true", help="generate deterministic random chunk lengths")
    parser.add_argument("--min-line-width", type=int, default=48, help="minimum width for random chunks")
    parser.add_argument("--max-line-width", type=int, default=192, help="maximum width for random chunks")
    parser.add_argument("--seed", type=int, default=0, help="seed for deterministic random chunk lengths")
    parser.add_argument("--repeat", type=int, default=3, help="repeat count for each strategy")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    line_width = max(1, args.line_width)
    min_line_width = max(1, args.min_line_width)
    max_line_width = max(min_line_width, args.max_line_width)
    chunks = make_chunks(
        count=max(1, args.chunks),
        line_width=line_width,
        random_lengths=args.random_lengths,
        min_line_width=min_line_width,
        max_line_width=max_line_width,
        seed=args.seed,
    )
    repeat = max(1, args.repeat)
    total_chars = sum(len(chunk) for chunk in chunks)
    chunk_lengths = [len(chunk) for chunk in chunks]

    results = [
        ("plus_equal", *benchmark_plus_equal(chunks=chunks, repeat=repeat)),
        ("plus_equal_aliased", *benchmark_plus_equal_aliased(chunks=chunks, repeat=repeat)),
        ("record_rebuild", *benchmark_record_rebuild(chunks=chunks, repeat=repeat)),
        ("list_join", *benchmark_list_join(chunks=chunks, repeat=repeat)),
        ("string_io", *benchmark_string_io(chunks=chunks, repeat=repeat)),
    ]
    fastest = min(elapsed for _, elapsed, _ in results)

    print("Python string append benchmark")
    print(f"chunks={len(chunks)}")
    print(f"line_width={line_width}")
    print(f"random_lengths={args.random_lengths}")
    if args.random_lengths:
        print(f"random_line_width_range={min_line_width}..{max_line_width}")
        print(f"seed={args.seed}")
    print(f"chunk_chars_min={min(chunk_lengths)}")
    print(f"chunk_chars_max={max(chunk_lengths)}")
    print(f"repeat={repeat}")
    print(f"final_chars={total_chars}")
    print("")
    for name, elapsed_ms, produced_size in results:
        ratio = elapsed_ms / fastest if fastest else 1.0
        print(f"{name}: {elapsed_ms:.2f}ms ratio={ratio:.2f}x produced_chars={produced_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
