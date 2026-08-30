"""
CLI wrapper for ai-factory

Thin wrapper over the library API with no business logic.
"""
import sys
import argparse
from .config import Config
from .config_loader import load_config
from .runner import run, list_models, embed
from .ledger_analysis import analyze_ledger, format_summary


def cmd_run(args) -> int:
    """
    Run command: execute a prompt.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Use config loader with CLI arguments as overrides
    config = load_config(
        provider=args.provider,
        model=args.model,
        max_retries=args.max_retries,
        backoff_base_ms=args.backoff_base_ms,
        backoff_multiplier=args.backoff_multiplier,
        ledger_enabled=not args.no_ledger,
        ledger_path=args.ledger_path,
        ledger_format=args.ledger_format,
        capture_prompt=args.capture_prompt,
        capture_output=args.capture_output,
        capture_limit_chars=args.capture_limit_chars,
    )
    
    result = run(args.prompt, config)
    
    # Print output to stdout
    if result.output:
        print(result.output)
    
    # Print metrics summary to stderr
    metrics = result.metrics
    print(f"\n--- Metrics ---", file=sys.stderr)
    print(f"Success: {metrics.success}", file=sys.stderr)
    print(f"Input chars: {metrics.input_chars}", file=sys.stderr)
    print(f"Output chars: {metrics.output_chars}", file=sys.stderr)
    print(f"Latency: {metrics.latency_ms}ms", file=sys.stderr)
    
    return 0 if result.success else 1


def cmd_models(args) -> int:
    """
    Models command: list available models.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Use config loader for provider configuration
    # Model field doesn't matter for listing
    config = load_config(
        provider=args.provider,
        model="dummy",  # Not used for listing
    )
    
    try:
        models = list_models(args.provider, config)
        
        print(f"Available models for provider '{args.provider}':\n")
        for model in models:
            print(f"  {model.name}")
            if model.context_window is not None:
                print(f"    Context window: {model.context_window}")
            if model.input_cost_per_1k is not None:
                print(f"    Input cost: ${model.input_cost_per_1k:.4f} per 1k tokens")
            if model.output_cost_per_1k is not None:
                print(f"    Output cost: ${model.output_cost_per_1k:.4f} per 1k tokens")
            if model.metadata:
                desc = model.metadata.get("description")
                if desc:
                    print(f"    {desc}")
            print()
        
        return 0
    
    except NotImplementedError:
        print("Model listing not supported for this provider", file=sys.stderr)
        return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_embed(args) -> int:
    """
    Embed command: generate embeddings for text.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Use config loader with CLI arguments as overrides
    config = load_config(
        provider=args.provider,
        model=args.model,
        ledger_enabled=not args.no_ledger,
        ledger_path=args.ledger_path,
        ledger_format=args.ledger_format,
    )
    
    # Read text from file or argument
    if args.text_file:
        try:
            with open(args.text_file, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            return 1
    elif args.text:
        text = args.text
    else:
        print("Error: Either --text or --text-file must be provided", file=sys.stderr)
        return 1
    
    result = embed(text, config)
    
    # Output vector to stdout or file
    if args.output:
        try:
            import json
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result.vector, f)
            print(f"Vector written to {args.output}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing output: {e}", file=sys.stderr)
            return 1
    else:
        # Print to stdout
        import json
        print(json.dumps(result.vector))
    
    # Print metrics summary to stderr
    metrics = result.metrics
    print(f"\n--- Metrics ---", file=sys.stderr)
    print(f"Success: {metrics.success}", file=sys.stderr)
    print(f"Input chars: {metrics.input_chars}", file=sys.stderr)
    print(f"Vector dim: {len(result.vector)}", file=sys.stderr)
    print(f"Latency: {metrics.latency_ms}ms", file=sys.stderr)
    
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
    
    return 0 if result.success else 1


def cmd_ledger_summary(args) -> int:
    """
    Ledger summary command: analyze and display ledger statistics.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    import os
    
    ledger_path = args.path
    
    if not os.path.exists(ledger_path):
        print(f"Ledger file not found: {ledger_path}", file=sys.stderr)
        print("Run some commands with --capture-prompt and --capture-output to populate the ledger.", file=sys.stderr)
        return 0  # Exit cleanly
    
    try:
        summary = analyze_ledger(ledger_path)
        output = format_summary(summary)
        print(output)
        return 0
    
    except Exception as e:
        print(f"Error analyzing ledger: {e}", file=sys.stderr)
        return 1


def cmd_pricing(args) -> int:
    """
    Pricing command: show the price table's contents and age, or rebuild it.

    Refresh is deliberately manual - `run()` never fetches prices on its own,
    so execution stays deterministic and offline-safe.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    from .pricing import (
        DEFAULT_MAX_AGE_DAYS,
        load_pricing_table,
        refresh_pricing_table,
    )

    max_age = args.max_age_days if args.max_age_days is not None else DEFAULT_MAX_AGE_DAYS

    if args.action == "refresh":
        try:
            count, path = refresh_pricing_table(args.path)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(f"Wrote {count} price entries to {path}")
        return 0

    table = load_pricing_table(args.path)
    print(f"Price table: {table.path}")

    if not table.prices:
        print("No prices loaded. Populate it with: ai-factory pricing refresh")
        return 0

    age = table.age_days()
    age_text = f"{age} day(s) old" if age is not None else "undated"
    status = "STALE" if table.is_stale(max_age) else "ok"
    print(f"Entries: {len(table.prices)}  |  Age: {age_text}  |  Status: {status} (limit {max_age} days)")

    if table.is_stale(max_age):
        print("Prices are still used, but costs may be wrong. Refresh with: ai-factory pricing refresh")

    print()
    print(f"{'PROVIDER':<12} {'MODEL':<40} {'IN $/M':>9} {'OUT $/M':>9} {'CACHE RD':>9}")
    for provider, model in sorted(table.prices):
        p = table.prices[(provider, model)]
        cache_read = f"{p.cache_read_per_1m:.3f}" if p.cache_read_per_1m is not None else "-"
        print(f"{provider:<12} {model:<40} {p.input_per_1m:>9.3f} {p.output_per_1m:>9.3f} {cache_read:>9}")
    return 0


def main() -> int:
    """
    Main CLI entrypoint.
    
    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="ai-factory",
        description="AI Factory - Minimal LLM execution"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Execute a prompt")
    run_parser.add_argument("--provider", help="Provider name (can be set in config file)")
    run_parser.add_argument("--model", help="Model name (can be set in config file)")
    run_parser.add_argument("--prompt", required=True, help="Input prompt")
    run_parser.add_argument("--max-retries", type=int, help="Max retries (default: 2)")
    run_parser.add_argument("--backoff-base-ms", type=int, help="Base backoff in ms (default: 250)")
    run_parser.add_argument("--backoff-multiplier", type=float, help="Backoff multiplier (default: 2.0)")
    run_parser.add_argument("--no-ledger", action="store_true", help="Disable ledger")
    run_parser.add_argument("--ledger-path", help="Ledger file path (default: ./LEDGER.is)")
    run_parser.add_argument("--ledger-format", choices=["is", "json"], help="Ledger format: 'is' (default) or 'json'")
    run_parser.add_argument("--capture-prompt", action="store_true", help="Capture prompt in ledger")
    run_parser.add_argument("--capture-output", action="store_true", help="Capture output in ledger")
    run_parser.add_argument("--capture-limit-chars", type=int, help="Capture limit in chars (default: 20000)")
    run_parser.set_defaults(func=cmd_run)
    
    # Models command
    models_parser = subparsers.add_parser("models", help="List available models")
    models_parser.add_argument("--provider", required=True, help="Provider name")
    models_parser.set_defaults(func=cmd_models)
    
    # Embed command
    embed_parser = subparsers.add_parser("embed", help="Generate embeddings for text")
    embed_parser.add_argument("--provider", help="Provider name (can be set in config file)")
    embed_parser.add_argument("--model", help="Model name (can be set in config file)")
    embed_parser.add_argument("--text", help="Input text to embed")
    embed_parser.add_argument("--text-file", help="Path to file containing text to embed")
    embed_parser.add_argument("--output", help="Output file path for vector (JSON format)")
    embed_parser.add_argument("--no-ledger", action="store_true", help="Disable ledger")
    embed_parser.add_argument("--ledger-path", help="Ledger file path (default: ./LEDGER.is)")
    embed_parser.add_argument("--ledger-format", choices=["is", "json"], help="Ledger format: 'is' (default) or 'json'")
    embed_parser.set_defaults(func=cmd_embed)
    
    # Ledger summary command
    ledger_parser = subparsers.add_parser("ledger-summary", help="Analyze and display ledger statistics")
    ledger_parser.add_argument("--path", default="./LEDGER.is", help="Path to LEDGER.is file (default: ./LEDGER.is)")
    ledger_parser.set_defaults(func=cmd_ledger_summary)

    # Pricing command
    pricing_parser = subparsers.add_parser("pricing", help="Show or refresh the model price table")
    pricing_parser.add_argument("action", choices=["show", "refresh"], help="show the table and its age, or rebuild it")
    pricing_parser.add_argument("--path", help="Price table path (default: ~/.aifactory/pricing.toml)")
    pricing_parser.add_argument("--max-age-days", type=int, default=None, help="Age in days past which prices are stale (default: 10)")
    pricing_parser.set_defaults(func=cmd_pricing)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
