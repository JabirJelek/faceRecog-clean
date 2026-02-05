#!/usr/bin/env python3
"""
Random Data Logger and Calculator
A script that captures random data, performs calculations, and logs to files.
"""

import random
import logging
import datetime
import os
import sys
import argparse
from pathlib import Path
from typing import Tuple

class RandomDataLogger:
    """Main class for capturing random data and performing calculations."""
    
    def __init__(self, log_dir: str = "logs"):
        """Initialize logger with log directory."""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.logger = None
        self.log_file = None
        
    def setup_logging(self, log_filename: str = None) -> None:
        """Configure logging to file and console."""
        if log_filename:
            self.log_file = self.log_dir / log_filename
        else:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = self.log_dir / f"random_calc_{timestamp}.txt"
        
        # Clear any existing handlers
        logging.getLogger().handlers.clear()
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging initialized: {self.log_file}")
    
    def generate_random_data(self) -> dict:
        """Generate random data of different types."""
        return {
            "integer": random.randint(1, 1000),
            "float": round(random.uniform(1.0, 100.0), 2),
            "string": f"DATA_{random.randint(1000, 9999)}",
            "timestamp": datetime.datetime.now().isoformat()
        }
    
    def perform_calculation(self, num1: float, num2: float) -> Tuple[str, float]:
        """Perform random mathematical calculation."""
        operations = {
            "add": lambda a, b: a + b,
            "subtract": lambda a, b: a - b,
            "multiply": lambda a, b: a * b,
            "divide": lambda a, b: a / b if b != 0 else float('inf'),
            "power": lambda a, b: a ** b,
            "modulus": lambda a, b: a % b if b != 0 else float('inf')
        }
        
        operation = random.choice(list(operations.keys()))
        result = operations[operation](num1, num2)
        
        # Format calculation string
        symbols = {
            "add": "+", "subtract": "-", "multiply": "*",
            "divide": "/", "power": "^", "modulus": "%"
        }
        
        calc_str = f"{num1} {symbols[operation]} {num2}"
        return calc_str, result
    
    def log_data_and_calculation(self) -> None:
        """Generate and log random data with calculation."""
        try:
            # Generate random data
            data = self.generate_random_data()
            
            # Generate calculation
            num1 = random.uniform(1.0, 50.0)
            num2 = random.uniform(1.0, 50.0)
            calculation, result = self.perform_calculation(num1, num2)
            
            # Log data
            self.logger.info("=" * 50)
            self.logger.info("GENERATED RANDOM DATA:")
            for key, value in data.items():
                self.logger.info(f"  {key}: {value}")
            
            # Log calculation
            self.logger.info("MATHEMATICAL CALCULATION:")
            self.logger.info(f"  {calculation} = {result:.4f}")
            
            # Additional info
            self.logger.info(f"Calculation type: {type(result).__name__}")
            if isinstance(result, float):
                self.logger.info(f"Result rounded: {round(result, 2)}")
            
        except Exception as e:
            self.logger.error(f"Error processing data: {str(e)}")
    
    def run(self, iterations: int = 10, output_file: str = None) -> None:
        """Run the logging process for specified iterations."""
        if output_file:
            self.setup_logging(output_file)
        else:
            self.setup_logging()
            
        self.logger.info(f"Starting data capture ({iterations} iterations)")
        self.logger.info(f"Log directory: {self.log_dir.absolute()}")
        
        for i in range(iterations):
            self.logger.info(f"\n--- Iteration {i + 1}/{iterations} ---")
            self.log_data_and_calculation()
        
        self.logger.info("\n" + "=" * 50)
        self.logger.info("Data capture completed successfully")
        
        # Show log file info
        self.print_summary()
    
    def print_summary(self) -> None:
        """Print summary of log files."""
        log_files = list(self.log_dir.glob("*.txt"))
        if log_files:
            latest_log = max(log_files, key=os.path.getctime)
            print("\n" + "=" * 50)
            print("PROGRAM SUMMARY")
            print("=" * 50)
            print(f"Latest log file: {latest_log}")
            print(f"File size: {latest_log.stat().st_size} bytes")
            print(f"File created: {datetime.datetime.fromtimestamp(latest_log.stat().st_ctime)}")
            print("\nRecent log files:")
            for log in sorted(log_files, key=os.path.getctime, reverse=True)[:3]:
                print(f"  - {log.name} ({log.stat().st_size} bytes)")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Random Data Logger and Calculator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run with default settings (10 iterations)
  %(prog)s -i 20             # Run 20 iterations
  %(prog)s -i 50 -o mylog.txt  # Run 50 iterations, save to mylog.txt
  %(prog)s -d custom_logs    # Use custom log directory
  %(prog)s -h                # Show this help message
        """
    )
    
    parser.add_argument(
        "-i", "--iterations",
        type=int,
        default=10,
        help="Number of iterations to run (default: 10, max: 1000)"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Custom output filename (e.g., 'mylog.txt')"
    )
    
    parser.add_argument(
        "-d", "--directory",
        type=str,
        default="logs",
        help="Log directory (default: 'logs')"
    )
    
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress console output (logs still saved to file)"
    )
    
    return parser.parse_args()

def main():
    """Main execution function."""
    # Parse command line arguments
    args = parse_arguments()
    
    # Validate iterations
    if args.iterations < 1 or args.iterations > 1000:
        print("Error: Iterations must be between 1 and 1000", file=sys.stderr)
        sys.exit(1)
    
    # Create logger instance
    logger = RandomDataLogger(args.directory)
    
    # Set up console output suppression
    if args.silent:
        sys.stdout = open(os.devnull, 'w')
    
    try:
        print("Random Data Logger and Calculator")
        print("=" * 40)
        print(f"Iterations: {args.iterations}")
        print(f"Log directory: {args.directory}")
        if args.output:
            print(f"Output file: {args.output}")
        print("-" * 40)
        
        # Run the logger
        logger.run(
            iterations=args.iterations,
            output_file=args.output
        )
        
        if not args.silent:
            print("\nProgram completed successfully!")
            print("Check the log directory for output files.")
        
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}", file=sys.stderr)
        if logger.logger:
            logger.logger.error(f"Program error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()