#!/usr/bin/env python3
"""
Merge every four bytes in a hex file into a single 32-bit number (little-endian).
"""

import argparse
import sys
from pathlib import Path


def merge_hex_bytes(input_file: str, output_file: str | None = None) -> str:
    """
    Merge every four bytes in a hex file into a 32-bit number.
    
    Args:
        input_file: Path to the input file
        output_file: Path to the output file (optional, outputs to stdout if not specified)
    
    Returns:
        The converted content string
    """
    with open(input_file, 'r') as f:
        content = f.read()
    
    lines = content.strip().split('\n')
    result_lines = []
    byte_buffer = []
    
    def flush_buffer():
        """Merge bytes in the buffer into a 32-bit number and add to results"""
        nonlocal byte_buffer
        while byte_buffer:
            # Take up to 4 bytes
            chunk = byte_buffer[:4]
            byte_buffer = byte_buffer[4:]
            
            # If less than 4 bytes, pad with zeros (little-endian, so high bytes are at the end)
            while len(chunk) < 4:
                chunk.append('00')
            
            # Little-endian merge: the first byte is the least significant, the fourth is most significant.
            # So we need to reverse the order.
            merged = ''.join(reversed(chunk)).upper()
            result_lines.append(merged)
    
    for line in lines:
        line = line.strip()
        
        if not line:
            continue
        
        # Check for segment marker (starts with @)
        if line.startswith('@'):
            # Process any existing data in buffer first
            flush_buffer()
            # Add segment marker
            result_lines.append(line)
        else:
            # Parse byte data (may be separated by spaces or other delimiters)
            # Supports "37 01 02 00" or "37010200" formats
            parts = line.split()
            for part in parts:
                # If it's a single byte (2 hex chars)
                if len(part) == 2:
                    byte_buffer.append(part)
                else:
                    # If continuous bytes (no spaces), treat every 2 chars as a byte
                    for i in range(0, len(part), 2):
                        if i + 2 <= len(part):
                            byte_buffer.append(part[i:i+2])
    
    # Process remaining bytes
    flush_buffer()
    
    result = '\n'.join(result_lines)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(result)
            f.write('\n')
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Merge every four bytes in a hex file into a 32-bit number (little-endian)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
dat:
  %(prog)s input.hex                    # Output to stdout
  %(prog)s input.hex -o output.hex      # Output to file
  %(prog)s input.hex --output output.hex
'''
    )
    
    parser.add_argument(
        'input',
        type=str,
        help='Input hex file path'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Output file path (outputs to stdout if not specified)'
    )
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not Path(args.input).exists():
        print(f"Error: Input file '{args.input}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    try:
        result = merge_hex_bytes(args.input, args.output)
        
        if not args.output:
            print(result)
        else:
            print(f"Successfully converted and saved to '{args.output}'", file=sys.stderr)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
