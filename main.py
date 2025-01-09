from fastapi import FastAPI, HTTPException
from typing import Optional

app = FastAPI(
    servers=[
        {
            "url": "https://gpt-stripe-store-main-for-nexus1e-git-main-christoss-projects.vercel.app/",
            "description": "Production environment"
        }
    ]
)

# Define a dictionary to map moods to colors
mood_color_mapping = {
    "happy": "yellow",
    "sad": "blue",
    "angry": "red",
    "relaxed": "green",
    "excited": "orange",
    "bored": "gray"
}

@app.get("/getColorByMood")
async def get_color_by_mood(mood: str):
    """
    Get a color based on the mood.
    :param mood: The mood for which to return the associated color.
    """
    mood = mood.lower()
    if mood in mood_color_mapping:
        return {"mood": mood, "color": mood_color_mapping[mood]}
    else:
        raise HTTPException(status_code=404, detail="Mood not found")

# Health check endpoint
@app.get("/")
async def health_check():
    return {"message": "The getColorByMood API is live!"}
