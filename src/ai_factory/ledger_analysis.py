"""
Read-only ledger analysis for ai-factory.

Parses LEDGER.is (append-only run blocks) and produces summary statistics.
Does NOT modify runner, providers, metrics, or ledger write logic.
"""
import os
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field


@dataclass
class RunRecord:
    """Represents a parsed run record from the ledger."""
    provider: str
    model: str
    success: bool
    attempts: int
    input_chars: int = 0
    output_chars: int = 0
    latency_ms: int = 0
    cost_usd: Optional[float] = None
    retry_count: int = 0


@dataclass
class ProviderStats:
    """Statistics for a single provider."""
    run_count: int = 0
    success_count: int = 0
    total_latency_ms: int = 0
    total_cost_usd: float = 0.0
    cost_entries: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.run_count == 0:
            return 0.0
        return (self.success_count / self.run_count) * 100.0
    
    @property
    def average_latency_ms(self) -> float:
        """Calculate average latency in milliseconds."""
        if self.run_count == 0:
            return 0.0
        return self.total_latency_ms / self.run_count
    
    @property
    def average_cost_usd(self) -> Optional[float]:
        """Calculate average cost in USD if available."""
        if self.cost_entries == 0:
            return None
        return self.total_cost_usd / self.cost_entries


@dataclass
class LedgerSummary:
    """Summary statistics from ledger analysis."""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_input_chars: int = 0
    total_output_chars: int = 0
    total_latency_ms: int = 0
    total_cost_usd: float = 0.0
    cost_entries: int = 0
    total_retry_count: int = 0
    runs_with_retries: int = 0
    max_latency_ms: int = 0
    min_latency_ms: Optional[int] = None
    provider_stats: Dict[str, ProviderStats] = field(default_factory=dict)
    model_counts: Dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate_percent(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_runs == 0:
            return 0.0
        return (self.successful_runs / self.total_runs) * 100.0
    
    @property
    def average_latency_ms(self) -> float:
        """Calculate average latency in milliseconds."""
        if self.total_runs == 0:
            return 0.0
        return self.total_latency_ms / self.total_runs
    
    @property
    def average_input_chars(self) -> float:
        """Calculate average input characters."""
        if self.total_runs == 0:
            return 0.0
        return self.total_input_chars / self.total_runs
    
    @property
    def average_output_chars(self) -> float:
        """Calculate average output characters."""
        if self.total_runs == 0:
            return 0.0
        return self.total_output_chars / self.total_runs
    
    @property
    def total_cost_usd_if_available(self) -> Optional[float]:
        """Return total cost if any cost data was recorded."""
        if self.cost_entries == 0:
            return None
        return self.total_cost_usd
    
    @property
    def most_used_model(self) -> Optional[str]:
        """Return the most frequently used model."""
        if not self.model_counts:
            return None
        return max(self.model_counts.items(), key=lambda x: x[1])[0]


def _parse_simple_value(line: str) -> Optional[str]:
    """Parse a simple value like (success true) or (provider "gemini")."""
    line = line.strip()
    if not line.startswith("(") or not line.endswith(")"):
        return None
    
    # Remove parentheses
    content = line[1:-1].strip()
    parts = content.split(None, 1)
    if len(parts) != 2:
        return None
    
    value = parts[1]
    # Remove quotes if present
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
        # Unescape
        value = value.replace('\\"', '"').replace('\\\\', '\\')
    
    return value


def _parse_run_block(block: str) -> Optional[RunRecord]:
    """
    Parse a single (run ...) block into a RunRecord.
    
    Returns None if the block is malformed or incomplete.
    """
    lines = block.strip().split('\n')
    if not lines or not lines[0].strip().startswith("(run"):
        return None
    
    record = RunRecord(
        provider="unknown",
        model="unknown",
        success=False,
        attempts=1
    )
    
    in_metrics = False
    in_retries = False
    retry_count = 0
    
    for line in lines[1:]:
        stripped = line.strip()
        
        # Handle section markers
        if stripped.startswith("(metrics"):
            in_metrics = True
            continue
        elif stripped.startswith("(retries"):
            in_retries = True
            continue
        elif stripped == ")":
            if in_metrics:
                in_metrics = False
            elif in_retries:
                in_retries = False
            continue
        
        # Parse values
        if in_retries and stripped.startswith("(retry"):
            retry_count += 1
        elif in_metrics:
            if "(input_chars" in stripped:
                val = _parse_simple_value(stripped)
                if val:
                    try:
                        record.input_chars = int(val)
                    except ValueError:
                        pass
            elif "(output_chars" in stripped:
                val = _parse_simple_value(stripped)
                if val:
                    try:
                        record.output_chars = int(val)
                    except ValueError:
                        pass
            elif "(latency_ms" in stripped:
                val = _parse_simple_value(stripped)
                if val:
                    try:
                        record.latency_ms = int(val)
                    except ValueError:
                        pass
            elif "(cost_usd" in stripped:
                val = _parse_simple_value(stripped)
                if val:
                    try:
                        record.cost_usd = float(val)
                    except ValueError:
                        pass
        else:
            if stripped.startswith("(provider"):
                val = _parse_simple_value(stripped)
                if val:
                    record.provider = val
            elif stripped.startswith("(model"):
                val = _parse_simple_value(stripped)
                if val:
                    record.model = val
            elif stripped.startswith("(success"):
                val = _parse_simple_value(stripped)
                if val:
                    record.success = val.lower() == "true"
            elif stripped.startswith("(attempts"):
                val = _parse_simple_value(stripped)
                if val:
                    try:
                        record.attempts = int(val)
                    except ValueError:
                        pass
    
    record.retry_count = retry_count
    return record


def parse_ledger(ledger_path: str) -> List[RunRecord]:
    """
    Parse LEDGER.is file and extract run records.
    
    Handles malformed trailing blocks gracefully by ignoring them.
    
    Args:
        ledger_path: Path to LEDGER.is file
        
    Returns:
        List of RunRecord objects
    """
    if not os.path.exists(ledger_path):
        return []
    
    with open(ledger_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split into run blocks - find all (run ... ) blocks
    records = []
    current_block = []
    depth = 0
    in_run = False
    
    for line in content.split('\n'):
        stripped = line.strip()
        
        if stripped.startswith("(run"):
            in_run = True
            current_block = [line]
            depth = 1
        elif in_run:
            current_block.append(line)
            # Track depth
            depth += stripped.count('(') - stripped.count(')')
            
            # If we've closed the run block
            if depth == 0:
                block_text = '\n'.join(current_block)
                record = _parse_run_block(block_text)
                if record:
                    records.append(record)
                in_run = False
                current_block = []
    
    # Ignore any incomplete trailing block (depth != 0)
    
    return records


def compute_summary(records: List[RunRecord]) -> LedgerSummary:
    """
    Compute summary statistics from run records.
    
    Args:
        records: List of RunRecord objects
        
    Returns:
        LedgerSummary with computed statistics
    """
    summary = LedgerSummary()
    
    for record in records:
        summary.total_runs += 1
        
        if record.success:
            summary.successful_runs += 1
        else:
            summary.failed_runs += 1
        
        summary.total_input_chars += record.input_chars
        summary.total_output_chars += record.output_chars
        summary.total_latency_ms += record.latency_ms
        
        if record.cost_usd is not None:
            summary.total_cost_usd += record.cost_usd
            summary.cost_entries += 1
        
        if record.retry_count > 0:
            summary.total_retry_count += record.retry_count
            summary.runs_with_retries += 1
        
        # Track min/max latency
        if summary.min_latency_ms is None or record.latency_ms < summary.min_latency_ms:
            summary.min_latency_ms = record.latency_ms
        if record.latency_ms > summary.max_latency_ms:
            summary.max_latency_ms = record.latency_ms
        
        # Track model usage
        summary.model_counts[record.model] = summary.model_counts.get(record.model, 0) + 1
        
        # Per-provider stats
        if record.provider not in summary.provider_stats:
            summary.provider_stats[record.provider] = ProviderStats()
        
        pstats = summary.provider_stats[record.provider]
        pstats.run_count += 1
        if record.success:
            pstats.success_count += 1
        pstats.total_latency_ms += record.latency_ms
        if record.cost_usd is not None:
            pstats.total_cost_usd += record.cost_usd
            pstats.cost_entries += 1
    
    return summary


def format_summary(summary: LedgerSummary) -> str:
    """
    Format summary as human-readable text.
    
    Args:
        summary: LedgerSummary object
        
    Returns:
        Formatted string for display
    """
    lines = [
        "AI Factory Ledger Summary",
        "=" * 40,
        f"Total Runs: {summary.total_runs}",
        f"Successful: {summary.successful_runs}",
        f"Failed: {summary.failed_runs}",
        f"Success Rate: {summary.success_rate_percent:.2f}%",
        "",
        f"Average Latency: {summary.average_latency_ms:.0f} ms",
        f"Max Latency: {summary.max_latency_ms} ms",
    ]
    
    if summary.min_latency_ms is not None:
        lines.append(f"Min Latency: {summary.min_latency_ms} ms")
    
    lines.extend([
        "",
        f"Average Input Chars: {summary.average_input_chars:.0f}",
        f"Average Output Chars: {summary.average_output_chars:.0f}",
        f"Total Input Chars: {summary.total_input_chars}",
        f"Total Output Chars: {summary.total_output_chars}",
        "",
        f"Total Retries: {summary.total_retry_count}",
        f"Runs with Retries: {summary.runs_with_retries}",
    ])
    
    if summary.total_cost_usd_if_available is not None:
        lines.extend([
            "",
            f"Total Cost: ${summary.total_cost_usd_if_available:.4f}",
        ])
    
    if summary.most_used_model:
        lines.extend([
            "",
            f"Most Used Model: {summary.most_used_model} ({summary.model_counts[summary.most_used_model]} runs)",
        ])
    
    # Per-provider breakdown
    if summary.provider_stats:
        lines.extend([
            "",
            "Per Provider Breakdown:",
            "-" * 40,
        ])
        
        for provider, stats in sorted(summary.provider_stats.items()):
            lines.append(f"  {provider}:")
            lines.append(f"    Runs: {stats.run_count}")
            lines.append(f"    Success Rate: {stats.success_rate:.2f}%")
            lines.append(f"    Avg Latency: {stats.average_latency_ms:.0f} ms")
            if stats.average_cost_usd is not None:
                lines.append(f"    Avg Cost: ${stats.average_cost_usd:.6f}")
            lines.append("")
    
    return '\n'.join(lines)


def analyze_ledger(ledger_path: str = "./LEDGER.is") -> LedgerSummary:
    """
    Analyze ledger file and return summary statistics.
    
    Args:
        ledger_path: Path to LEDGER.is file (default: ./LEDGER.is)
        
    Returns:
        LedgerSummary object with computed statistics
    """
    records = parse_ledger(ledger_path)
    return compute_summary(records)
