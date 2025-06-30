# Paper Finder & Downloader

A Python GUI application that helps you find and download academic papers using DOI or title search, with Sci-Hub integration.

## Features

- **DOI or Title Search**: Enter either a DOI (Digital Object Identifier) or paper title to find the corresponding paper
- **Title-to-DOI Resolution**: Automatically converts paper titles to DOIs using CrossRef and OA.mg APIs
- **Multi-Domain Sci-Hub Support**: Tries multiple Sci-Hub domains to find available papers
- **PDF Download**: Directly download located PDFs with a single click
- **Threaded Operations**: Runs network operations in separate threads to keep the UI responsive
- **Progress Feedback**: Shows real-time status updates during search and download operations

## Requirements

- Python 3.x
- Required packages:
  - `tkinter` (usually included with Python)
  - `requests`
  - `beautifulsoup4`

Install dependencies with:
```
pip install requests beautifulsoup4
```

## Usage

1. Run the script: `python paper_finder.py`
2. Enter either:
   - A DOI (e.g., `10.1038/nature12373`)
   - A paper title (e.g., "Deep learning for computer vision")
3. Click "Search & Download"
4. Once found, click "Download PDF" to save the paper

## Technical Details

- Uses CrossRef and OA.mg APIs for title-to-DOI resolution
- Attempts multiple Sci-Hub domains for reliability
- Parses Sci-Hub pages to find PDF iframe sources
- Includes proper user-agent headers for API requests
- Provides detailed status updates in the UI

## Disclaimer

This tool is provided for educational purposes only. Please respect copyright laws and only download papers you are legally entitled to access. The developers are not responsible for how this tool is used.

## Screenshot

[Would include an image of the GUI here if available]

## License

MIT License - Free for personal and educational use
