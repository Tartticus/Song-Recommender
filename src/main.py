import tkinter as tk
from tkinter import ttk, messagebox
import requests
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from bs4 import BeautifulSoup
import re
import os
import threading
import nltk
import duckdb

# Initialize Sentiment Analyzer
nltk.download('vader_lexicon')
sid = SentimentIntensityAnalyzer()

# Replace with your Genius API token
GENIUS_API_TOKEN = 'zMs-ogdbxt0F5CzmO52iLZ9A3jgj3ZZQWvNTNyTSm05x7z7yaLgWSlJFMa7cX92f'

# Initialize DuckDB connection
con = duckdb.connect(database='lyrics.db')  # Use a persistent DuckDB database file
con.execute('''
    CREATE TABLE IF NOT EXISTS lyrics (
        artist TEXT,
        title TEXT,
        lyrics TEXT,
        sentiment_score REAL
    )
''')

def normalize_text(text):
    text = re.sub(r'[^a-zA-Z0-9 ]', '', text)
    return text.lower()

def analyze_sentiment(text):
    sentiment_score = sid.polarity_scores(text)
    return sentiment_score['compound']

def closest_sentiment(dict_obj, given_score):
    closest_key = None
    closest_difference = float('inf')  # Initialize with a large number
    
    for key, value in dict_obj.items():
        sentiment_score = value['sentiment_scores']['compound']
        difference = abs(sentiment_score - given_score)
        
        if difference < closest_difference:
            closest_difference = difference
            closest_key = key
    
    return closest_key

def request_artist_info(artist_name, page):
    base_url = 'https://api.genius.com'
    headers = {'Authorization': f'Bearer {GENIUS_API_TOKEN}'}
    search_url = f'{base_url}/search?per_page=10&page={page}'
    data = {'q': artist_name}
    response = requests.get(search_url, data=data, headers=headers)
    return response

def request_song_url(artist_name, song_cap):
    page = 1
    songs = []
    
    while True:
        response = request_artist_info(artist_name, page)
        json = response.json()
        
        song_info = []
        for hit in json['response']['hits']:
            if artist_name.lower() in hit['result']['primary_artist']['name'].lower():
                song_info.append(hit)
                
        for song in song_info:
            if len(songs) < song_cap:
                url = song['result']['url']
                songs.append(url)
            
        if len(songs) == song_cap:
            break
        else:
            page += 1
        
    print(f'loading {len(songs)} of {artist_name}s newest songs')
    return songs

def scrape_song_lyrics(url):
    page = requests.get(url)
    html = BeautifulSoup(page.text, 'html.parser')
    lyrics_div = html.find('div', class_='lyrics')
    
    if lyrics_div:
        lyrics = lyrics_div.get_text()
    else:
        lyrics = html.find_all('div', class_=re.compile('Lyrics__Container'))
        lyrics = "\n".join([div.get_text(separator="\n").strip() for div in lyrics])

    lyrics = re.sub(r'[\(\[].*?[\)\]]', '', lyrics)  # Remove identifiers like chorus, verse, etc.
    lyrics = os.linesep.join([s for s in lyrics.splitlines() if s])  # Remove empty lines
    return lyrics

def store_lyrics_in_db(artist, title, lyrics, sentiment_score):
    artist = normalize_text(artist)
    con.execute('''
        INSERT INTO lyrics (artist, title, lyrics, sentiment_score)
        VALUES (?, ?, ?, ?)
    ''', (artist, title, lyrics, sentiment_score))

def get_lyrics_from_db(artist_name):
    artist_name = normalize_text(artist_name)
    result = con.execute('''
        SELECT title, lyrics, sentiment_score FROM lyrics
        WHERE artist = ?
    ''', (artist_name,)).fetchall()
    return result

def scrape_lyrics(artist_name, song_cap):
    db_lyrics = get_lyrics_from_db(artist_name)
    
    if db_lyrics:
        song_lyrics = {title: {'text': lyrics, 'sentiment_scores': {'compound': sentiment_score}} for title, lyrics, sentiment_score in db_lyrics}
    else:
        songs = request_song_url(artist_name, song_cap)
        song_lyrics = {}
        for url in songs:
            title = url.split("/")[-1].replace("-lyrics", "").replace("-", " ").title()
            lyrics = scrape_song_lyrics(url)
            sentiment_score = analyze_sentiment(lyrics)
            song_lyrics[title] = {'text': lyrics, 'sentiment_scores': {'compound': sentiment_score}}
            store_lyrics_in_db(artist_name, title, lyrics, sentiment_score)
    
    return song_lyrics

def recommend_song():
    loading_label.config(text="Loading song recommendation...", foreground="blue")
    root.update_idletasks()
    
    user_sentiment_text = mood_entry.get()
    user_sentiment_score = analyze_sentiment(user_sentiment_text)
    artist_name = artist_entry.get()
    song_cap = 100
    
    try:
        Lyrics = scrape_lyrics(artist_name, song_cap)
        for key, text in Lyrics.items():
            scores = text['sentiment_scores']
            Lyrics[key] = {
                'text': text['text'],
                'sentiment_scores': scores,
                'sentiment_label': 'positive' if scores['compound'] > 0 else 'negative' if scores['compound'] < 0 else 'neutral'
            }
        song = closest_sentiment(Lyrics, user_sentiment_score)
        loading_label.config(text=f"You should listen to {song}", foreground="green")
    except Exception as e:
        loading_label.config(text="")
        messagebox.showerror("Error", str(e))

def start_recommendation_thread():
    recommendation_thread = threading.Thread(target=recommend_song)
    recommendation_thread.start()

# Tkinter GUI setup
root = tk.Tk()
root.title("Song Recommendation Based on Mood")

style = ttk.Style()
style.configure("TLabel", font=("Arial", 12), padding=10)
style.configure("TEntry", font=("Arial", 12))
style.configure("TButton", font=("Arial", 12), padding=10)
style.configure("TFrame", padding=10)

frame = ttk.Frame(root)
frame.grid(padx=20, pady=20)

ttk.Label(frame, text="How are you feeling?").grid(row=0, column=0, sticky=tk.W, pady=5)
mood_entry = ttk.Entry(frame, width=50)
mood_entry.grid(row=0, column=1, pady=5)

ttk.Label(frame, text="Who do you want to listen to?:").grid(row=1, column=0, sticky=tk.W, pady=5)
artist_entry = ttk.Entry(frame, width=50)
artist_entry.grid(row=1, column=1, pady=5)

ttk.Button(frame, text='Get Recommendation', command=start_recommendation_thread).grid(row=3, column=1, pady=20)

loading_label = ttk.Label(frame, text="", font=("Arial", 10, "italic"))
loading_label.grid(row=4, column=1, pady=5)

root.mainloop()
