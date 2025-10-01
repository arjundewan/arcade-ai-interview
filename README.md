# Arcade AI Interview Challenge

Welcome to the Arcade AI Interview Challenge! This project tests your ability to work with AI multimodal APIs, and be creative with your problem solving

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- An OpenAI API key with access to `gpt-4o-mini` and `gpt-image-1`

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Your API Key

Create a `.env` file in the project root with your OpenAI API key:
OPENAI_API_KEY=your-api-key-here

Optional (cost control):
ENABLE_CACHE=1

> **Note:** The `.env` file is already in `.gitignore` for your security.

### 3. Run the Project

To generate the summary markdown and social image, run:

```bash
python flow_parser.py
# or specify a custom input file
python flow_parser.py path/to/flow.json
```

- This will read `flow.json` and output:

  - `output/flow_summary.md` (the markdown report)
  - `output/flow_social_image.png` (the social media image)

  The output directory already contains a sample report and image as an example.

### 4. Caching (Cost Management)

This project includes simple on-disk caching for API responses to control cost and speed up iteration.

- Summary cache: `.cache/summary-*.md`
- Image cache: `.cache/image-*.png`

Controls:

- Enable/disable via `ENABLE_CACHE=1` (default) or `ENABLE_CACHE=0` in your environment or `.env`.
- Clear cache: `rm -rf .cache/`

## 🎯 Challenge Overview

You've been provided with a `flow.json` file that contains data from an Arcade flow recording. Your task is to build a script that analyzes this flow data and creates a comprehensive report.

## 📋 Requirements

Your application should accomplish the following:

1. **Identify User Interactions**: List out the actions the user did in a human readable format (i.e. "Clicked on checkout", "Search for X")
2. **Generate Human-Friendly Summary**: Create a clear, readable summary of what the user was trying to accomplish
3. **Create a Social Media Image**: Generate an creative image suitable for sharing on social platforms that represents the flow and would drive engagement

These items should be then displayed in a **markdown file** that can be committed in your project

## 🛠️ Technical Requirements

- **Language**: Any
- **AI Integration**: You will be provided an OpenAI API key, but feel free to use providers you have accounts with
- **Version Control**: Use GitHub/Bitbucket to track your work - we want to see your development process and commit history

## 🔒 Security Note

**IMPORTANT**: Never commit your API key to version control! Use environment variables or a `.env` file (and add it to `.gitignore`) to keep your API key secure.

## 📁 Project Structure

You'll be provided with:

- `flow.json` - The flow data to analyze
- OpenAI API key

Your application should generate:

- A comprehensive markdown report
- A social media image file

## 🎨 Arcade Flow Reference

The flow data comes from this Arcade recording: https://app.arcade.software/share/2RnSqfsV4EsODmUiPKoW

You can view the original flow to understand what the user was doing, your solution should be general purpose enough to work for most Arcade flows.

## 💡 Hints

- The `flow.json` contains different types of steps (IMAGE, CHAPTER, VIDEO, etc.)
- Each step has metadata about what the user clicked and when
- Think about how to structure your analysis for maximum clarity
- The social media image should be professional and represent the flow's purpose
- Feel free to use different models types to both understand the flow and generate the image

## 💰 Cost Management

We do have API limits, and since you'll likely run this script multiple times during development and testing, we strongly recommend implementing caching for expensive API responses.

This will help you stay within API rate limits and keep costs manageable while iterating on your solution.

## Good luck!

We're excited to see your creative approach to this challenge.
