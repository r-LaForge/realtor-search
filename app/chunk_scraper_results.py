import csv
from pathlib import Path


class ChunkResults:
    """Chunks CSV scraper results into smaller files for batch processing."""

    def __init__(self, chunk_size: int = 30):
        self.chunk_size = chunk_size
        self.output_dir = Path("../scraper-output/chunks")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def chunk_results(self, input_csv: str) -> list[str]:
        """
        Chunk a CSV file into smaller files.

        Args:
            input_csv: Path to input CSV file

        Returns:
            List of output chunk file paths
        """
        # Read all rows from input CSV
        with open(input_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            all_rows = list(reader)

        print(f"Read {len(all_rows)} rows from {input_csv}")

        # Calculate number of chunks
        num_chunks = (len(all_rows) + self.chunk_size - 1) // self.chunk_size
        print(f"Creating {num_chunks} chunks of {self.chunk_size} rows each...")

        chunk_files = []

        # Create chunk files
        for chunk_idx in range(num_chunks):
            start_idx = chunk_idx * self.chunk_size
            end_idx = min(start_idx + self.chunk_size, len(all_rows))
            chunk_rows = all_rows[start_idx:end_idx]

            # Write chunk file
            chunk_filename = f"chunk-{chunk_idx + 1}.csv"
            chunk_path = self.output_dir / chunk_filename

            with open(chunk_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(chunk_rows)

            chunk_files.append(str(chunk_path))
            print(f"✓ Created {chunk_filename} ({len(chunk_rows)} rows)")

        print(f"\n✓ Chunking complete. Created {len(chunk_files)} files in {self.output_dir}")
        return chunk_files


def main():
    """Example usage."""
    chunker = ChunkResults(chunk_size=30)
    chunks = chunker.chunk_results("../scraper-output/scraper-output-all.csv")
    print(f"\nGenerated chunks: {chunks}")


if __name__ == "__main__":
    main()