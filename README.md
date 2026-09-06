# 👗 Meesho AI Video Script & Flow Director

A Streamlit application designed for creators and fashion sellers to generate high-converting short-form video scripts (15-30s Reels & YouTube Shorts), zero-moderation Google Flow & Kling AI video prompts, and ready-to-copy Instagram launch kits.

## 🚀 Features
- **Dual-Image Multimodal Conditioning**: Locks identity from Creator Photo and ground truth from Meesho Catalog Photo.
- **Auto-Sanitized Garment Crop**: Automatically extracts a ghost-mannequin crop without skin or faces to eliminate AI video policy rejections.
- **Battle-Tested Google Flow Prompts**: Strict lexical cloaking with Section 8C structure and negative safety blocks.
- **Zivame / Clovia Style 2-Piece Rule**: Top worn + panty held in hands for intimate wear reviews.
- **Instagram Launch Kit**: High-retention caption, ManyChat DM automation keyword, pinned comment, and 20 viral hashtags.

## 🛠️ Deploy on Streamlit Community Cloud
1. Fork or upload this repository to your GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and click **New App**.
3. Select your repository and set `Main file path` to `streamlit_app.py`.
4. In **Advanced Settings > Secrets**, add your Gemini API Key:
```toml
GEMINI_API_KEY = "your_gemini_api_key_here"
```
5. Click **Deploy**!
