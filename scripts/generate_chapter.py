#!/usr/bin/env python3
"""
The Willowbrook Mysteries — Continuous Cozy Mystery Generation Engine

A companion to the Neverending Story Engine, but a distinct genre: a gentle,
Agatha-Christie-flavoured English village mystery series, using real UK news
headlines (general/local news, not cyber/tech) as the seed for each new case.

Reuses the proven pattern: direct Ollama text-completion calls (no agent
tool-calling), atomic exFAT-safe writes, sentence-completion validation,
inline markdown-to-HTML rendering, and a self-contained Kindle-style reader.
"""

import os
import json
import random
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import time
import re
import sys

def get_base_dir():
    if os.path.exists('/projects'):
        return '/projects'
    return '/Volumes/SSK Drive /apps'

def safe_write_file(target_path, content):
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    tmp_path = target_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp_path, target_path)

BASE_DIR = get_base_dir()
OLLAMA_HOST = "http://192.168.0.141:11434"

TOP_MODELS = [
    'qwen2.5-coder:7b',
    'qwen2.5-coder:14b',
    'qwen2.5-coder:32b',
    'mistral-small3.1:latest',
    'gemma3:12b',
]
FALLBACK_MODEL = 'qwen2.5-coder:7b'

TONES = [
    'Gentle Cosy Mystery (tea, gossip, a puzzle over scones)',
    'Wry Village Comedy-of-Manners (petty rivalries, a fete gone wrong)',
    'Autumnal Whodunit (mist over the green, a secret from decades past)',
    'Warm-Hearted Amateur Sleuth Caper (unlikely clues, a chase on bicycles)',
    'Quietly Unsettling Village Mystery (something is not quite right at the manor)'
]

# Deliberately avoids general/breaking news feeds (BBC UK, Guardian UK, etc.)
# — those routinely carry crime, death and tragedy, which is not appropriate
# raw material for a gentle cosy mystery even with a "fictionalise it" prompt.
# Stick to sources that are inherently light by design, and still run every
# headline through UNSAFE_HEADLINE_PATTERN below as a second line of defence.
NEWS_RSS_FEEDS = [
    {
        'name': 'BBC News (Explainers)',
        'url': 'http://feeds.bbci.co.uk/news/explainers/rss.xml',
        'category': 'Curiosities & Everyday Mysteries'
    },
    {
        'name': 'Good News Network',
        'url': 'https://www.goodnewsnetwork.org/feed/',
        'category': 'Uplifting & Community News'
    },
    {
        'name': 'BBC News (Technology)',
        'url': 'http://feeds.bbci.co.uk/news/technology/rss.xml',
        'category': 'Curious Technology & Innovation'
    },
    {
        'name': 'BBC News (Science & Environment)',
        'url': 'http://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
        'category': 'Nature & Curious Science'
    },
]

# Skip any headline containing these — a safety net on top of using
# inherently gentle feeds, in case a dark item still slips through.
UNSAFE_HEADLINE_PATTERN = re.compile(
    r'\b(murder|stabb|shoot|kill|dead|death|dies|died|attack|abuse|rape|assault|'
    r'terror|bomb|war\b|massacre|suicide|overdose|fire kills|crash kills|'
    r'child abuse|grooming|trafficking|hostage)\b',
    re.IGNORECASE
)

INITIAL_CHARACTERS = [
    {
        'id': 'char_marigold',
        'name': 'Marigold Pemberton-Hale',
        'role': 'Retired Detective Inspector, now runs the village bookshop',
        'avatar': '🕵️‍♀️📚',
        'status': 'Quietly cataloguing new arrivals while keeping one ear on village gossip',
        'personality': 'Sharp-eyed, dryly witty, deceptively unhurried, misses nothing.',
        'location': 'Pemberton Books, on the corner of Willow Lane, Willowbrook-on-Fen',
        'backstory': 'Thirty years with the Yard before retiring to her late aunt\'s bookshop. Insists she is done with detective work. She is not.',
        'inventory': ['Battered leather notebook', 'Reading glasses on a chain', 'A rather good magnifying glass', 'Thermos of Earl Grey'],
        'relationships': {'Reverend Aubrey Finch': 'Old friend and reluctant partner-in-snooping (Trust: 91%)', 'PC Nesbit': 'Fond but exasperated (Trust: 70%)'},
        'arcHistory': ['Solved the matter of the vanishing church silver quietly, without telling anyone.', 'Reluctantly agreed the bookshop needed a "Mystery" section after all.'],
        'lastObservedUk': time.strftime('%d/%m/%y %H:%M')
    },
    {
        'id': 'char_aubrey',
        'name': 'Reverend Aubrey Finch',
        'role': 'Vicar of St. Wilfred\'s, amateur historian, terrible gossip',
        'avatar': '⛪️🧣',
        'status': 'Pretending to work on Sunday\'s sermon while listening at the vestry door',
        'personality': 'Kind, curious to a fault, hopelessly nosy, surprisingly good at cards.',
        'location': 'St. Wilfred\'s Church, Willowbrook-on-Fen',
        'backstory': 'Came to Willowbrook twelve years ago from London and never left. Knows every family secret in the parish register.',
        'inventory': ['Dog-eared parish records', 'A bicycle called Bertha', 'Emergency biscuit tin', 'Reading spectacles, usually lost'],
        'relationships': {'Marigold Pemberton-Hale': 'Partner-in-crime-solving, mostly against his will (Trust: 91%)', 'Mrs. Ottoline Vance': 'Wary respect (Trust: 60%)'},
        'arcHistory': ['Accidentally revealed a fifty-year-old scandal during a christening.', 'Won the village fete raffle three years running, which some find suspicious.'],
        'lastObservedUk': time.strftime('%d/%m/%y %H:%M')
    },
    {
        'id': 'char_ottoline',
        'name': 'Mrs. Ottoline Vance',
        'role': 'Owner of the Willowbrook Tearoom, unofficial mayor of village opinion',
        'avatar': '☕️🧁',
        'status': 'Behind the counter, hearing absolutely everything',
        'personality': 'Formidable, warm underneath it, terrifyingly well-informed, loyal.',
        'location': 'The Willowbrook Tearoom, the Green, Willowbrook-on-Fen',
        'backstory': 'Has run the tearoom for thirty years. Nothing happens in Willowbrook that does not pass through her counter first.',
        'inventory': ['A tray that never wobbles', 'A ledger of who owes what gossip', 'Spare umbrella for regulars', 'A truly excellent Victoria sponge recipe'],
        'relationships': {'Marigold Pemberton-Hale': 'Trusted confidante (Trust: 88%)', 'Reverend Aubrey Finch': 'Wary respect, mutual (Trust: 60%)'},
        'arcHistory': ['Once refused to serve the Mayor his usual until he apologised to the postman.', 'Keeps a "suspicious behaviour" ledger she insists is just for the parish newsletter.'],
        'lastObservedUk': time.strftime('%d/%m/%y %H:%M')
    }
]

def load_or_init_book():
    base = get_base_dir()
    book_file = os.path.join(base, 'willowbrook-mysteries/public/story_chronicles.json')
    data = None
    if os.path.exists(book_file):
        try:
            with open(book_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            pass

    if not isinstance(data, dict):
        data = {}

    if 'bookTitle' not in data:
        data['bookTitle'] = 'The Willowbrook Mysteries'
    if 'subtitle' not in data:
        data['subtitle'] = 'Small Village. Large Curiosity. Continuous Cases Synthesised by Edge Intelligence'
    if 'author' not in data:
        data['author'] = 'Edge LLM Collective & Autonomous Multi-Agent System'
    if 'lastUpdatedUk' not in data:
        data['lastUpdatedUk'] = time.strftime('%d/%m/%y %H:%M')
    if 'characters' not in data or not data['characters']:
        data['characters'] = INITIAL_CHARACTERS
    if 'usedSourceHeadlines' not in data:
        data['usedSourceHeadlines'] = []
    if 'chapters' not in data:
        data['chapters'] = []
    if 'totalChapters' not in data:
        data['totalChapters'] = len(data['chapters'])
    if 'totalWords' not in data:
        data['totalWords'] = sum(c.get('wordCount', 0) for c in data['chapters'])

    for c in data.get('characters', []):
        if 'arcHistory' not in c:
            c['arcHistory'] = [c.get('backstory', 'Initial entry in character chronicle.')]
        if 'avatar' not in c:
            c['avatar'] = '👤'
        if 'status' not in c:
            c['status'] = 'About the village'

    return data

def fetch_random_news_story(used_headlines):
    shuffled_feeds = list(NEWS_RSS_FEEDS)
    random.shuffle(shuffled_feeds)

    for feed_info in shuffled_feeds:
        print(f"📡 Polling Live Feed: {feed_info['name']} ({feed_info['url']})...")
        try:
            req = urllib.request.Request(feed_info['url'], headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
            with urllib.request.urlopen(req, timeout=7) as resp:
                xml_data = resp.read()
                root = ET.fromstring(xml_data)

                items = root.findall('.//item')
                random.shuffle(items)

                for item in items:
                    title_elem = item.find('title')
                    desc_elem = item.find('description')
                    link_elem = item.find('link')

                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''
                    desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ''
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ''

                    clean_desc = re.sub(r'<[^>]+>', ' ', desc).strip()
                    clean_desc = re.sub(r'\s+', ' ', clean_desc)

                    if title and UNSAFE_HEADLINE_PATTERN.search(title):
                        print(f"⛔ Skipping unsuitable headline: '{title}'")
                        continue

                    if title and title not in used_headlines:
                        print(f"✓ Selected Unique Story from {feed_info['name']}: '{title}'")
                        return {
                            'headline': title,
                            'category': feed_info['category'],
                            'sourceUrl': link,
                            'extractedContextSnippet': clean_desc[:350] if clean_desc else f"Real-world news item reported by {feed_info['name']}."
                        }
        except Exception as e:
            print(f"⚠️ Notice: Could not fetch {feed_info['name']} ({e}). Trying next feed...", file=sys.stderr)

    seq = len(used_headlines) + 1
    return {
        'headline': f'A Curious Small Matter Reported in the Willowbrook Parish Newsletter (Case #{seq})',
        'category': 'Curiosities & Everyday Mysteries',
        'sourceUrl': '',
        'extractedContextSnippet': 'An unremarkable-seeming event that will, of course, turn out not to be unremarkable at all.'
    }

ABBREVIATIONS = {
    'mr', 'mrs', 'ms', 'mx', 'dr', 'prof', 'rev', 'st', 'sr', 'jr',
    'mt', 'ave', 'etc', 'vs', 'no', 'approx', 'capt', 'col', 'gen', 'lt', 'sgt'
}

def _ends_with_abbreviation(s):
    m = re.search(r'([A-Za-z]+)\.\s*$', s)
    return bool(m and m.group(1).lower() in ABBREVIATIONS)

def validate_and_ensure_sentence_integrity(prose_text):
    text = prose_text.strip()
    if not text:
        return "The tearoom fell quiet, as if the village itself were waiting to see what happened next."

    non_ambiguous_terminals = ('!', '?', '!"', '?"', '..."', '’', '”', '"')
    if text.endswith(non_ambiguous_terminals):
        return text
    if text.endswith('.') and not _ends_with_abbreviation(text):
        return text

    # Walk sentence-boundary candidates from the end, skipping any that are
    # actually an abbreviation (e.g. "...spoke to Mrs. " is not a real end).
    candidates = list(re.finditer(r'[\.\!\?]["”’\']?\s+', text))
    for m in reversed(candidates):
        end_pos = m.end()
        candidate_text = text[:end_pos].strip()
        if not _ends_with_abbreviation(candidate_text):
            print(f"🔧 Sentence Validator: Pruned {len(text) - len(candidate_text)} trailing incomplete characters.")
            return candidate_text

    return text + " — and there, for now, the matter rested."

def query_edge_llm(model, prompt):
    print(f"🤖 Querying Edge LLM: {model}...")
    try:
        payload = json.dumps({
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {'temperature': 0.75, 'num_predict': 600, 'top_p': 0.9}
        }).encode('utf-8')

        req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('response', '').strip(), model
    except Exception as e:
        print(f"⚠️ Model '{model}' notice ({e}). Fallback to '{FALLBACK_MODEL}'...", file=sys.stderr)
        try:
            payload = json.dumps({
                'model': FALLBACK_MODEL,
                'prompt': prompt,
                'stream': False,
                'options': {'temperature': 0.6, 'num_predict': 500}
            }).encode('utf-8')
            req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=18) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get('response', '').strip(), FALLBACK_MODEL
        except Exception:
            return None, "deterministic_engine"

def evolve_characters_with_llm(characters, new_chapter):
    print("🧠 Evolving character profiles with Edge LLM...")
    prompt = f"""You are the Series Editor overseeing character continuity for an ongoing British cosy mystery series.

**Latest Chapter Summary ({new_chapter['title']}):**
{new_chapter['subtitle']}
{new_chapter['contentMarkdown'][:400]}...

**Current Character Roster:**
{json.dumps([{'id': c['id'], 'name': c['name'], 'location': c['location'], 'status': c['status']} for c in characters], indent=2)}

**Task:**
Provide updated status, location, and one new key development for each of the 3 characters based on this chapter.
Output strictly JSON matching this structure:
{{
  "char_marigold": {{ "status": "[Updated state]", "location": "[Current location]", "newArcEvent": "[One concise sentence of new development]" }},
  "char_aubrey": {{ "status": "[Updated state]", "location": "[Current location]", "newArcEvent": "[One concise sentence of new development]" }},
  "char_ottoline": {{ "status": "[Updated state]", "location": "[Current location]", "newArcEvent": "[One concise sentence of new development]" }}
}}"""

    response_text, _ = query_edge_llm('qwen2.5-coder:7b', prompt)
    try:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            evolutions = json.loads(json_match.group(0))
            for c in characters:
                cid = c['id']
                if cid in evolutions:
                    evo = evolutions[cid]
                    if evo.get('status'): c['status'] = evo['status']
                    if evo.get('location'): c['location'] = evo['location']
                    if evo.get('newArcEvent'):
                        c['arcHistory'].append(f"Chapter {new_chapter['chapterNumber']}: {evo['newArcEvent']}")
                    c['lastObservedUk'] = time.strftime('%d/%m/%y %H:%M')
            print("✓ Successfully evolved character roster and updated arc history.")
            return
    except Exception as e:
        print(f"⚠️ Character evolution notice ({e}). Appending chapter milestone.", file=sys.stderr)

    for c in characters:
        c['arcHistory'].append(f"Chapter {new_chapter['chapterNumber']}: Actively involved in '{new_chapter['title']}'.")
        c['lastObservedUk'] = time.strftime('%d/%m/%y %H:%M')

def generate_chapter_prose(chapter_num, feed, tone, characters, previous_chapters):
    prev_summary = ""
    if previous_chapters:
        last_ch = previous_chapters[-1]
        prev_summary = f"Previous Chapter ({last_ch['title']}): {last_ch['subtitle']} — {last_ch['contentMarkdown'][:180]}..."

    char_desc = "\n".join([f"- **{c['name']}** ({c['role']}) at {c['location']}. Status: {c['status']}." for c in characters])

    prompt = f"""You are a Master Novelist writing Chapter {chapter_num} of a continuous British cosy mystery series set in the fictional village of Willowbrook-on-Fen.

**World Context & Active Characters:**
{char_desc}

**Previous Story Thread:**
{prev_summary if prev_summary else "This is Chapter 1. Establish the village of Willowbrook-on-Fen and the small, curious matter that draws Marigold's attention."}

**Real-World News Item Loosely Inspiring This Chapter's Small Mystery (fictionalise it completely — invent a village-scale mystery in the same spirit, do not report real events or name real people):**
- Headline: {feed['headline']}
- Category: {feed['category']}
- Context: {feed['extractedContextSnippet']}

**Tone & Atmospheric Genre for this Chapter:**
{tone}

**Mandatory Writing Directives:**
1. Write strictly in **British English** (e.g. colour, centre, favourite, travelling, autumn).
2. Keep it gentle and cosy — no graphic violence, nothing grim. This is Agatha Christie warmth, not true crime.
3. Focus on sensory village detail: tea, hedgerows, church bells, the tearoom, gossip over the counter.
4. MUST END ON A COMPLETE, FINISHED SENTENCE with a small, intriguing hook for next time.
5. Format output:
TITLE: [Evocative Chapter Title]
SUBTITLE: [One-line witty synopsis]
[3-4 Paragraphs of Chapter Prose in Markdown]"""

    chosen_model = random.choice(TOP_MODELS)
    response_text, model_used = query_edge_llm(chosen_model, prompt)

    if not response_text:
        response_text = """TITLE: The Matter of the Missing Marmalade
SUBTITLE: Someone in Willowbrook has a secret, and it smells faintly of oranges.

The bell above Pemberton Books gave its familiar half-hearted jingle as Marigold looked up from the ledger she was pretending to balance. Outside, the September mist was doing its usual trick of making the village green look like something from a watercolour nobody had quite finished. She was not, she told herself firmly, looking for a mystery.

The Reverend Aubrey Finch arrived moments later on Bertha, his bicycle, considerably out of breath and considerably more interested in gossip than exercise. "Marigold," he said, without preamble, "Ottoline says the church fete marmalade has gone missing. All forty jars. Overnight."

Marigold set down her pen with the particular care of someone who has just decided, against her own better judgement, to be interested after all. "Forty jars of marmalade," she said, "do not simply walk away, Aubrey."

"No," he agreed, "but I rather think someone walked away with them."""

    lines = [l.strip() for l in response_text.split('\n') if l.strip()]
    title = f"Chapter {chapter_num}: A Small Willowbrook Matter"
    subtitle = "Something curious is afoot."
    content_lines = []

    title_pattern = re.compile(r'^\**\s*title\s*\**\s*:\s*', re.IGNORECASE)
    subtitle_pattern = re.compile(r'^\**\s*subtitle\s*\**\s*:\s*', re.IGNORECASE)

    for line in lines:
        if title_pattern.match(line):
            title = title_pattern.sub('', line).strip().strip('*\'" ')
        elif subtitle_pattern.match(line):
            subtitle = subtitle_pattern.sub('', line).strip().strip('*\'" ')
        else:
            content_lines.append(line)

    raw_prose = "\n\n".join(content_lines)
    # Strip any unprompted meta-commentary the model appends (e.g. "Hook for
    # Next Time:", "---", "Author's note:") before sentence validation, since
    # these are not part of the story and often trail off mid-sentence.
    meta_marker_pattern = re.compile(
        r'\n\n(?:-{2,}\s*\n\n)?\**\s*(hook for next time|author.?s note|to be continued|end of chapter)\s*:?.*',
        re.IGNORECASE | re.DOTALL
    )
    raw_prose = meta_marker_pattern.sub('', raw_prose).strip()
    validated_prose = validate_and_ensure_sentence_integrity(raw_prose)

    word_count = len(validated_prose.split())
    reading_time = max(1, round(word_count / 200))

    return {
        'chapterNumber': chapter_num,
        'title': title,
        'subtitle': subtitle,
        'contentMarkdown': validated_prose,
        'wordCount': word_count,
        'readingTimeMinutes': reading_time,
        'modelUsed': model_used,
        'tone': tone.split(' (')[0],
        'sourceTrigger': feed,
        'generatedAtUk': time.strftime('%d/%m/%y %H:%M'),
        'charactersInvolved': ['Marigold Pemberton-Hale', 'Reverend Aubrey Finch', 'Mrs. Ottoline Vance']
    }

def markdown_inline_to_html(text):
    escaped = (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'__(.+?)__', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', escaped)
    escaped = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<em>\1</em>', escaped)
    return escaped

def dicebear_avatar_url(seed, style='adventurer'):
    """Free, no-API-key SVG avatar. https://www.dicebear.com — stable, static URL."""
    import urllib.parse
    q = urllib.parse.quote(seed)
    return f"https://api.dicebear.com/9.x/{style}/svg?seed={q}&backgroundType=gradientLinear&backgroundColor=f4e9d8,e8d5b7"

def chapter_header_image_url(chapter_num, width=800, height=320):
    """Free, no-API-key placeholder photo, seeded so it's stable across rebuilds.
    https://picsum.photos — no key, no rate-limit auth needed for this volume."""
    return f"https://picsum.photos/seed/willowbrook-{chapter_num}/{width}/{height}"

def compile_kindle_html_reader(book):
    total_chapters = len(book['chapters'])
    chapters_html = ""

    avatar_by_name = {c['name']: dicebear_avatar_url(c['id']) for c in book['characters']}

    toc_items = "".join([
        f"""<li class="toc-item">
              <button class="toc-link" onclick="scrollToChapter({ch['chapterNumber']})">
                <span class="toc-num">{ch['chapterNumber']}</span>
                <span class="toc-text">
                  <strong>{markdown_inline_to_html(ch['title'])}</strong>
                  <em>{markdown_inline_to_html(ch['subtitle'])}</em>
                </span>
              </button>
            </li>"""
        for ch in book['chapters']
    ])

    for idx, ch in enumerate(book['chapters']):
        ch_num = ch['chapterNumber']
        is_last = (idx == total_chapters - 1)
        next_ch_num = ch_num + 1 if not is_last else None
        prev_ch_num = ch_num - 1 if ch_num > 1 else None
        header_img = chapter_header_image_url(ch_num)

        paragraphs = ch['contentMarkdown'].split('\n\n')
        paras_html = "".join([f"<p>{markdown_inline_to_html(p.strip())}</p>" for p in paragraphs if p.strip()])

        featuring_html = "".join([
            f'<span class="featuring-avatar" title="{name}"><img src="{avatar_by_name[name]}" alt="{name}" width="28" height="28" loading="lazy"></span>'
            for name in ch.get('charactersInvolved', []) if name in avatar_by_name
        ])

        bottom_nav_html = ""
        if next_ch_num:
            bottom_nav_html = f"""
            <div class="chapter-footer-nav">
              <button class="ch-nav-btn next" onclick="scrollToChapter({next_ch_num})">
                <span>Continue to Chapter {next_ch_num}</span>
                <span class="btn-arrow">➔</span>
              </button>
            </div>
            """
        else:
            bottom_nav_html = f"""
            <div class="chapter-footer-nav latest-badge">
              <span class="pulse-dot"></span>
              <strong>You have reached the latest chapter (Chapter {ch_num}).</strong>
              <p>A new case unfolds automatically.</p>
            </div>
            """

        chapters_html += f"""
        <details class="chapter-details" id="chapter-{ch_num}" data-chapter-index="{ch_num}" open>
          <summary class="chapter-summary">
            <div class="summary-left">
              <span class="chapter-badge">Chapter {ch_num}</span>
              <strong class="summary-title">{markdown_inline_to_html(ch['title'])}</strong>
            </div>
            <div class="summary-right">
              <span class="summary-pill">{ch['readingTimeMinutes']} min read</span>
              <span class="summary-pill">{ch['wordCount']} words</span>
              <span class="summary-pill tone">{ch['tone']}</span>
              <span class="chevron">▼</span>
            </div>
          </summary>

          <article class="chapter-body">
            <img class="chapter-hero-img" src="{header_img}" alt="" loading="lazy" width="800" height="320">
            <header class="chapter-header">
              <div class="chapter-subtitle">{markdown_inline_to_html(ch['subtitle'])}</div>
              <div class="featuring-row">
                <span class="featuring-label">Featuring</span>
                {featuring_html}
              </div>
              <div class="chapter-meta-line">
                <span>Model: <strong>{ch['modelUsed']}</strong></span> •
                <span>Generated: {ch['generatedAtUk']} UK</span> •
                <span class="quick-nav-links">
                  {f'<a href="#chapter-{prev_ch_num}" onclick="scrollToChapter({prev_ch_num}); return false;" class="mini-link">◀ Prev Ch</a> •' if prev_ch_num else ''}
                  {f'<a href="#chapter-{next_ch_num}" onclick="scrollToChapter({next_ch_num}); return false;" class="mini-link">Next Ch ▶</a> •' if next_ch_num else ''}
                  <a href="#chapter-{total_chapters}" onclick="scrollToChapter({total_chapters}); return false;" class="mini-link highlight">Latest (Ch {total_chapters}) ⏩</a>
                </span>
              </div>

              <details class="source-story-details">
                <summary class="source-summary">
                  <span>📰 Real-World News Inspiration</span>
                  <span class="source-tag">{ch['sourceTrigger']['category']}</span>
                </summary>
                <div class="source-content">
                  <strong class="source-headline">{ch['sourceTrigger']['headline']}</strong>
                  <p class="source-snippet">{ch['sourceTrigger']['extractedContextSnippet']}</p>
                  {f'<a href="{ch["sourceTrigger"]["sourceUrl"]}" target="_blank" rel="noopener noreferrer" class="threat-link">🔗 Read the real article ➔</a>' if ch['sourceTrigger'].get('sourceUrl') else ''}
                </div>
              </details>
            </header>

            <div class="prose-content">
              {paras_html}
            </div>

            {bottom_nav_html}
          </article>
        </details>
        """

    characters_html = ""
    for c in book['characters']:
        inventory_pills = "".join([f"<span class='inv-pill'>🎒 {item}</span>" for item in c['inventory']])
        rel_lines = "".join([f"<div class='rel-line'><strong>{k}:</strong> {v}</div>" for k, v in c['relationships'].items()])
        arc_items = "".join([f"<li class='arc-item'>{event}</li>" for event in c['arcHistory']])

        avatar_url = dicebear_avatar_url(c['id'])
        characters_html += f"""
        <div class="character-card">
          <div class="char-header">
            <div class="char-avatar">
              <img src="{avatar_url}" alt="" loading="lazy" width="56" height="56">
              <span class="char-avatar-emoji">{c['avatar']}</span>
            </div>
            <div class="char-title-area">
              <div class="char-name-row">
                <h3 class="char-name">{c['name']}</h3>
                <span class="char-role-badge">{c['role']}</span>
              </div>
              <div class="char-location">📍 {c['location']}</div>
              <div class="char-status">⚡ <em>Status:</em> <strong>{c['status']}</strong></div>
            </div>
          </div>

          <p class="char-backstory">{c['backstory']}</p>

          <div class="char-section">
            <div class="char-section-title">Current Effects</div>
            <div class="inv-wrapper">{inventory_pills}</div>
          </div>

          <div class="char-section">
            <div class="char-section-title">Relationships</div>
            <div class="rel-wrapper">{rel_lines}</div>
          </div>

          <div class="char-section">
            <div class="char-section-title">Case History (Multi-Chapter Memory)</div>
            <ul class="arc-list">
              {arc_items}
            </ul>
          </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="paperwhite" data-font="bookerly" data-size="base" data-width="optimal" data-spacing="relaxed">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{book['bookTitle']} — Kindle Reader</title>
  <style>
    :root {{
      --bg: #f7efe1;
      --text: #3a2c1c;
      --header-bg: rgba(247, 239, 225, 0.95);
      --border: #e3d3ae;
      --card-bg: rgba(255, 255, 255, 0.72);
      --accent: #7a8f5c;
      --accent-2: #c17a63;
      --font-family: 'Bookerly', 'Georgia', serif;
      --font-size: 19px;
      --line-height: 1.8;
      --max-width: 760px;
      --paper-texture:
        radial-gradient(circle at 15% 20%, rgba(196, 164, 108, 0.05) 0%, transparent 45%),
        radial-gradient(circle at 85% 75%, rgba(122, 143, 92, 0.05) 0%, transparent 50%),
        radial-gradient(circle at 50% 50%, rgba(193, 122, 99, 0.03) 0%, transparent 60%);
    }}
    [data-theme="sepia"] {{
      --bg: #f4ecd8; --text: #2c2217; --header-bg: rgba(244, 236, 216, 0.95);
      --border: #d8cca8; --card-bg: rgba(255, 255, 255, 0.5); --accent: #78350f; --accent-2: #a8622f;
    }}
    [data-theme="dark"] {{
      --bg: #191510; --text: #ecdfc4; --header-bg: rgba(25, 21, 16, 0.95);
      --border: #3d3527; --card-bg: #241f17; --accent: #9bc17e; --accent-2: #d99678;
    }}
    [data-theme="mint"] {{
      --bg: #0d1b14; --text: #c2e0cb; --header-bg: rgba(13, 27, 20, 0.95);
      --border: #1f3d2a; --card-bg: #112519; --accent: #52d18a; --accent-2: #6fb8d9;
    }}
    [data-font="bookerly"] {{ --font-family: 'Bookerly', 'Georgia', serif; }}
    [data-font="georgia"] {{ --font-family: 'Georgia', 'Times New Roman', serif; }}
    [data-font="atkinson"] {{ --font-family: 'Atkinson Hyperlegible', sans-serif; }}
    [data-font="sans"] {{ --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    [data-size="sm"] {{ --font-size: 16px; }}
    [data-size="base"] {{ --font-size: 19px; }}
    [data-size="lg"] {{ --font-size: 22px; }}
    [data-size="xl"] {{ --font-size: 26px; }}
    [data-width="narrow"] {{ --max-width: 620px; }}
    [data-width="optimal"] {{ --max-width: 760px; }}
    [data-width="wide"] {{ --max-width: 940px; }}
    body {{ background-color: var(--bg); background-image: var(--paper-texture); color: var(--text); font-family: var(--font-family); font-size: var(--font-size); line-height: var(--line-height); margin: 0; padding: 0; transition: all 0.2s ease; cursor: default; }}
    .top-nav {{ position: sticky; top: 0; background: var(--header-bg); backdrop-filter: blur(10px); border-bottom: 1px solid var(--border); padding: 10px 20px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; z-index: 100; font-family: -apple-system, sans-serif; font-size: 13px; }}
    .nav-left {{ display: flex; align-items: center; gap: 14px; }}
    .nav-title {{ font-weight: 800; letter-spacing: 0.5px; color: var(--accent); text-transform: uppercase; }}
    .nav-tabs {{ display: flex; gap: 4px; background: rgba(0,0,0,0.05); padding: 3px; border-radius: 6px; border: 1px solid var(--border); }}
    .nav-tab-btn {{ background: transparent; border: none; color: var(--text); padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; }}
    .nav-tab-btn.active {{ background: var(--accent); color: #ffffff; }}
    .controls-group {{ display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }}
    .ctrl-btn {{ background: transparent; border: 1px solid var(--border); color: var(--text); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; transition: all 0.15s ease; }}
    .ctrl-btn:hover {{ border-color: var(--accent); background: rgba(0,0,0,0.05); }}
    .ctrl-btn.jump-latest {{ background: var(--accent); color: #ffffff; border-color: var(--accent); }}
    .floating-nav-hud {{ position: fixed; right: 20px; bottom: 70px; display: flex; flex-direction: column; gap: 8px; z-index: 99; font-family: -apple-system, sans-serif; }}
    .hud-btn {{ background: var(--header-bg); backdrop-filter: blur(12px); border: 1px solid var(--border); color: var(--text); padding: 8px 14px; border-radius: 20px; cursor: pointer; font-size: 12px; font-weight: bold; box-shadow: 0 4px 14px rgba(0,0,0,0.15); transition: transform 0.15s ease, background 0.15s ease; display: flex; align-items: center; gap: 6px; }}
    .hud-btn:hover {{ transform: translateY(-2px); border-color: var(--accent); color: var(--accent); }}
    .hud-btn.primary {{ background: var(--accent); color: #ffffff; border-color: var(--accent); }}
    .hud-btn.primary:hover {{ opacity: 0.9; color: #ffffff; }}
    .book-container {{ max-width: var(--max-width); margin: 0 auto; padding: 40px 20px 140px; transition: max-width 0.3s ease; }}
    .book-cover {{ text-align: center; margin-bottom: 40px; padding-bottom: 30px; border-bottom: 2px solid var(--border); }}
    .book-title {{ font-size: 2.2em; font-weight: 900; margin: 0 0 10px; line-height: 1.2; }}
    .book-subtitle {{ font-size: 1.1em; font-style: italic; opacity: 0.85; margin-bottom: 16px; }}
    .global-collapse-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; font-family: -apple-system, sans-serif; font-size: 13px; font-weight: bold; }}
    details.chapter-details {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; margin-bottom: 28px; overflow: hidden; scroll-margin-top: 80px; transition: box-shadow 0.2s ease, border-color 0.2s ease; box-shadow: 0 3px 14px rgba(60, 40, 20, 0.06); }}
    .chapter-hero-img {{ display: block; width: 100%; height: 220px; object-fit: cover; border-bottom: 1px solid var(--border); background: var(--border); }}
    .featuring-row {{ display: flex; align-items: center; gap: 6px; margin: 6px 0 12px; font-family: -apple-system, sans-serif; }}
    .featuring-label {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; color: var(--accent-2); margin-right: 4px; }}
    .featuring-avatar img {{ width: 28px; height: 28px; border-radius: 50%; border: 2px solid var(--card-bg); box-shadow: 0 0 0 1px var(--border); display: block; margin-left: -8px; }}
    .featuring-avatar:first-of-type img {{ margin-left: 0; }}
    .toc-box {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; margin-bottom: 28px; overflow: hidden; box-shadow: 0 3px 14px rgba(60, 40, 20, 0.06); }}
    .toc-box-summary {{ padding: 16px 20px; cursor: pointer; font-weight: 800; font-family: -apple-system, sans-serif; font-size: 14px; color: var(--accent-2); user-select: none; }}
    .toc-list {{ list-style: none; margin: 0; padding: 0 12px 12px; }}
    .toc-item {{ margin: 0 0 4px; }}
    .toc-link {{ width: 100%; text-align: left; background: transparent; border: none; border-radius: 10px; padding: 10px 12px; cursor: pointer; display: flex; align-items: center; gap: 12px; font-family: inherit; color: var(--text); transition: background 0.15s ease; }}
    .toc-link:hover {{ background: rgba(0,0,0,0.04); }}
    .toc-num {{ flex: none; width: 26px; height: 26px; border-radius: 50%; background: var(--accent); color: #fff; font-size: 12px; font-weight: 800; display: flex; align-items: center; justify-content: center; font-family: -apple-system, sans-serif; }}
    .toc-text {{ display: flex; flex-direction: column; gap: 1px; font-size: 14.5px; }}
    .toc-text em {{ font-family: -apple-system, sans-serif; font-size: 12px; opacity: 0.75; font-style: italic; }}
    details.chapter-details.focused {{ border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }}
    summary.chapter-summary {{ padding: 16px 20px; cursor: pointer; user-select: none; display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.02); border-bottom: 1px solid transparent; font-family: -apple-system, sans-serif; }}
    details.chapter-details[open] summary.chapter-summary {{ border-bottom: 1px solid var(--border); }}
    .summary-left {{ display: flex; align-items: center; gap: 10px; }}
    .chapter-badge {{ background: var(--accent); color: #ffffff; font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; }}
    .summary-title {{ font-size: 17px; font-weight: 800; }}
    .summary-right {{ display: flex; align-items: center; gap: 8px; }}
    .summary-pill {{ font-size: 11px; background: rgba(0,0,0,0.05); border: 1px solid var(--border); padding: 2px 8px; border-radius: 12px; font-weight: 600; }}
    .summary-pill.tone {{ background: rgba(63, 107, 79, 0.12); color: var(--accent); border-color: var(--accent); }}
    .chevron {{ font-size: 12px; transition: transform 0.2s ease; }}
    details.chapter-details[open] .chevron {{ transform: rotate(180deg); }}
    .chapter-body {{ padding: 28px 24px 20px; }}
    .chapter-header {{ margin-bottom: 24px; border-bottom: 1px solid var(--border); padding-bottom: 16px; }}
    .chapter-subtitle {{ font-size: 1.05em; font-style: italic; opacity: 0.85; margin-bottom: 8px; }}
    .chapter-meta-line {{ font-size: 12px; font-family: -apple-system, sans-serif; opacity: 0.8; margin-bottom: 14px; }}
    .quick-nav-links {{ margin-left: 8px; }}
    .mini-link {{ color: var(--text); text-decoration: underline; cursor: pointer; font-weight: 600; margin: 0 4px; }}
    .mini-link.highlight {{ color: var(--accent); font-weight: 800; }}
    details.source-story-details {{ background: rgba(0,0,0,0.03); border: 1px dashed var(--border); border-radius: 6px; margin: 12px 0; font-family: -apple-system, sans-serif; font-size: 12px; }}
    summary.source-summary {{ padding: 8px 12px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-weight: 700; color: var(--accent); }}
    .source-tag {{ background: rgba(0,0,0,0.08); padding: 1px 6px; border-radius: 3px; font-size: 10px; text-transform: uppercase; }}
    .source-content {{ padding: 10px 12px; border-top: 1px dashed var(--border); }}
    .source-headline {{ display: block; margin-bottom: 4px; }}
    .source-snippet {{ margin: 0; opacity: 0.8; font-size: 11.5px; }}
    .threat-link {{ color: var(--accent); font-size: 11px; text-decoration: underline; font-weight: bold; display: inline-block; margin-top: 6px; }}
    .prose-content p {{ margin-bottom: 24px; text-align: justify; text-justify: inter-word; hyphens: auto; }}
    .prose-content p:first-of-type::first-letter {{ font-size: 3.2em; float: left; line-height: 0.85; padding-right: 8px; padding-top: 4px; color: var(--accent); font-weight: bold; }}
    .chapter-footer-nav {{ margin-top: 32px; padding-top: 20px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; font-family: -apple-system, sans-serif; }}
    .ch-nav-btn {{ background: var(--accent); color: #ffffff; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; display: flex; align-items: center; gap: 8px; transition: opacity 0.15s ease, transform 0.15s ease; }}
    .ch-nav-btn:hover {{ opacity: 0.9; transform: translateX(3px); }}
    .chapter-footer-nav.latest-badge {{ display: flex; flex-direction: column; align-items: center; text-align: center; background: rgba(0,0,0,0.03); padding: 16px; border-radius: 6px; }}
    .pulse-dot {{ width: 10px; height: 10px; background: #10b981; border-radius: 50%; margin-bottom: 6px; box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.2); }}
    .character-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 24px; margin-bottom: 24px; box-shadow: 0 3px 14px rgba(60, 40, 20, 0.06); }}
    .char-header {{ display: flex; gap: 16px; align-items: flex-start; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 16px; }}
    .char-avatar {{ position: relative; flex: none; width: 72px; height: 72px; background: rgba(0,0,0,0.04); border-radius: 50%; border: 1px solid var(--border); overflow: visible; }}
    .char-avatar img {{ width: 100%; height: 100%; border-radius: 50%; display: block; }}
    .char-avatar-emoji {{ position: absolute; bottom: -4px; right: -4px; font-size: 20px; background: var(--card-bg); border: 1px solid var(--border); border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; line-height: 1; }}
    .char-title-area {{ flex: 1; }}
    .char-name-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 4px; }}
    .char-name {{ font-size: 22px; font-weight: 900; margin: 0; color: var(--accent); }}
    .char-role-badge {{ font-size: 11px; font-family: -apple-system, sans-serif; background: rgba(0,0,0,0.06); padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid var(--border); }}
    .char-location {{ font-size: 13px; font-family: -apple-system, sans-serif; opacity: 0.85; margin-bottom: 4px; }}
    .char-status {{ font-size: 13px; font-family: -apple-system, sans-serif; color: var(--accent); }}
    .char-backstory {{ font-size: 15px; font-style: italic; margin-bottom: 18px; opacity: 0.9; }}
    .char-section {{ margin-top: 14px; font-family: -apple-system, sans-serif; }}
    .char-section-title {{ font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; color: var(--accent); }}
    .inv-wrapper {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .inv-pill {{ font-size: 11px; background: rgba(0,0,0,0.05); border: 1px solid var(--border); padding: 3px 8px; border-radius: 4px; font-weight: 600; }}
    .rel-line {{ font-size: 12px; margin-bottom: 4px; }}
    .arc-list {{ margin: 0; padding-left: 20px; font-size: 13px; }}
    .arc-item {{ margin-bottom: 6px; }}
    .tab-content {{ display: none; }}
    .tab-content.active {{ display: block; }}
    .progress-bar-fixed {{ position: fixed; bottom: 0; left: 0; right: 0; background: var(--header-bg); border-top: 1px solid var(--border); padding: 8px 24px; display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-family: -apple-system, sans-serif; opacity: 0.95; z-index: 100; }}
    .cursor-help {{ font-size: 11px; opacity: 0.7; }}
  </style>
</head>
<body>

  <nav class="top-nav">
    <div class="nav-left">
      <div class="nav-title">📖 {book['bookTitle']}</div>
      <div class="nav-tabs">
        <button id="btnTabNovel" class="nav-tab-btn active" onclick="switchMainTab('novel')">📖 Read ({total_chapters})</button>
        <button id="btnTabCodex" class="nav-tab-btn" onclick="switchMainTab('codex')">👥 Cast ({len(book['characters'])})</button>
      </div>
    </div>
    <div class="controls-group">
      <button class="ctrl-btn jump-latest" onclick="scrollToChapter({total_chapters})">⚡ Latest (Ch {total_chapters})</button>
      <button class="ctrl-btn" onclick="setFontSize('sm')">A-</button>
      <button class="ctrl-btn" onclick="setFontSize('base')">A</button>
      <button class="ctrl-btn" onclick="setFontSize('lg')">A+</button>
      <button class="ctrl-btn" onclick="setFontSize('xl')">A++</button>
      <select onchange="setFontFamily(this.value)" class="ctrl-btn" style="background:var(--header-bg);">
        <option value="bookerly">Bookerly (Serif)</option>
        <option value="georgia">Georgia</option>
        <option value="atkinson">Atkinson (Accessible)</option>
        <option value="sans">System Sans</option>
      </select>
      <button class="ctrl-btn" onclick="setColumnWidth('narrow')">Narrow</button>
      <button class="ctrl-btn" onclick="setColumnWidth('optimal')">Optimal</button>
      <button class="ctrl-btn" onclick="setColumnWidth('wide')">Wide</button>
      <button class="ctrl-btn" onclick="setTheme('paperwhite')">Paperwhite</button>
      <button class="ctrl-btn" onclick="setTheme('sepia')">Sepia</button>
      <button class="ctrl-btn" onclick="setTheme('dark')">Dark</button>
      <button class="ctrl-btn" onclick="setTheme('mint')">Mint</button>
    </div>
  </nav>

  <aside class="floating-nav-hud">
    <button class="hud-btn primary" onclick="scrollToChapter({total_chapters})" title="Jump to latest (Press End or L)"><span>⏩ Latest (Ch {total_chapters})</span></button>
    <button class="hud-btn" onclick="scrollPrevChapter()" title="Previous chapter (Press ArrowLeft or P)"><span>▲ Prev Ch</span></button>
    <button class="hud-btn" onclick="scrollNextChapter()" title="Next chapter (Press ArrowRight or N)"><span>▼ Next Ch</span></button>
    <button class="hud-btn" onclick="scrollToChapter(1)" title="Return to Chapter 1 (Press Home)"><span>⏮️ Ch 1</span></button>
  </aside>

  <main class="book-container">
    <div id="tabNovel" class="tab-content active">
      <div class="book-cover">
        <h1 class="book-title">{book['bookTitle']}</h1>
        <div class="book-subtitle">{book['subtitle']}</div>
        <div style="font-size:12px; font-family:-apple-system,sans-serif; opacity:0.8;">
          Authored by Edge AI Collective • {total_chapters} Chapters • {book['totalWords']} Words • Real Headlines Woven In ✓
        </div>
      </div>
      <details class="toc-box" open>
        <summary class="toc-box-summary">📑 Table of Contents ({total_chapters} Chapters)</summary>
        <ol class="toc-list">
          {toc_items}
        </ol>
      </details>

      <div class="global-collapse-bar">
        <span>All Chapters</span>
        <div class="controls-group">
          <button class="ctrl-btn" onclick="toggleAllChapters(true)">📂 Expand All</button>
          <button class="ctrl-btn" onclick="toggleAllChapters(false)">📁 Collapse All</button>
        </div>
      </div>
      {chapters_html}
    </div>

    <div id="tabCodex" class="tab-content">
      <div class="book-cover">
        <h1 class="book-title">👥 The Willowbrook Cast</h1>
        <div class="book-subtitle">Persistent memory, evolving case history, updated after each chapter</div>
      </div>
      {characters_html}
    </div>
  </main>

  <div class="progress-bar-fixed">
    <span>The Willowbrook Mysteries ({total_chapters} Total Chapters)</span>
    <span class="cursor-help">⌨️ [◀ / ▶] Next/Prev • [End / L] Latest • [Home] Ch 1</span>
  </div>

  <script>
    const TOTAL_CHAPTERS = {total_chapters};
    let currentChapterIndex = 1;
    function scrollToChapter(chNum) {{
      if (chNum < 1) chNum = 1;
      if (chNum > TOTAL_CHAPTERS) chNum = TOTAL_CHAPTERS;
      currentChapterIndex = chNum;
      switchMainTab('novel');
      const el = document.getElementById('chapter-' + chNum);
      if (el) {{
        el.open = true;
        document.querySelectorAll('details.chapter-details').forEach(c => c.classList.remove('focused'));
        el.classList.add('focused');
        el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
    }}
    function scrollNextChapter() {{ if (currentChapterIndex < TOTAL_CHAPTERS) scrollToChapter(currentChapterIndex + 1); else scrollToChapter(TOTAL_CHAPTERS); }}
    function scrollPrevChapter() {{ if (currentChapterIndex > 1) scrollToChapter(currentChapterIndex - 1); }}
    window.addEventListener('keydown', (e) => {{
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
      if (e.key === 'ArrowRight' || e.key === 'n' || e.key === 'N') scrollNextChapter();
      else if (e.key === 'ArrowLeft' || e.key === 'p' || e.key === 'P') scrollPrevChapter();
      else if (e.key === 'End' || e.key === 'l' || e.key === 'L') scrollToChapter(TOTAL_CHAPTERS);
      else if (e.key === 'Home') scrollToChapter(1);
    }});
    function switchMainTab(tab) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-tab-btn').forEach(el => el.classList.remove('active'));
      if (tab === 'novel') {{ document.getElementById('tabNovel').classList.add('active'); document.getElementById('btnTabNovel').classList.add('active'); }}
      else {{ document.getElementById('tabCodex').classList.add('active'); document.getElementById('btnTabCodex').classList.add('active'); }}
    }}
    function setTheme(t) {{ document.documentElement.setAttribute('data-theme', t); localStorage.setItem('wb_theme', t); }}
    function setFontSize(s) {{ document.documentElement.setAttribute('data-size', s); localStorage.setItem('wb_size', s); }}
    function setFontFamily(f) {{ document.documentElement.setAttribute('data-font', f); localStorage.setItem('wb_font', f); }}
    function setColumnWidth(w) {{ document.documentElement.setAttribute('data-width', w); localStorage.setItem('wb_width', w); }}
    function toggleAllChapters(openState) {{ document.querySelectorAll('details.chapter-details').forEach(el => {{ el.open = openState; }}); }}
    if (localStorage.getItem('wb_theme')) setTheme(localStorage.getItem('wb_theme'));
    if (localStorage.getItem('wb_size')) setFontSize(localStorage.getItem('wb_size'));
    if (localStorage.getItem('wb_font')) setFontFamily(localStorage.getItem('wb_font'));
    if (localStorage.getItem('wb_width')) setColumnWidth(localStorage.getItem('wb_width'));
  </script>

</body>
</html>"""
    return html

def main():
    print("🚀 Running Willowbrook Mysteries Engine with Atomic File Persistence...")
    base = get_base_dir()
    book = load_or_init_book()

    chosen_feed = fetch_random_news_story(book['usedSourceHeadlines'])
    chosen_tone = random.choice(TONES)

    next_chapter_num = len(book['chapters']) + 1
    print(f"📖 Synthesising Chapter {next_chapter_num} with Trigger: '{chosen_feed['headline']}' ({chosen_feed['category']})...")
    print(f"🎨 Narrative Tone: {chosen_tone}")

    new_chapter = generate_chapter_prose(
        next_chapter_num,
        chosen_feed,
        chosen_tone,
        book['characters'],
        book['chapters']
    )

    book['chapters'].append(new_chapter)
    book['totalChapters'] = len(book['chapters'])
    book['totalWords'] = sum(c['wordCount'] for c in book['chapters'])
    book['usedSourceHeadlines'].append(chosen_feed['headline'])
    book['lastUpdatedUk'] = time.strftime('%d/%m/%y %H:%M')

    evolve_characters_with_llm(book['characters'], new_chapter)

    json_path = os.path.join(base, 'willowbrook-mysteries/public/story_chronicles.json')
    safe_write_file(json_path, json.dumps(book, indent=2))
    print(f"✓ Saved updated story chronicle to: {json_path}")

    html_content = compile_kindle_html_reader(book)
    public_html_path = os.path.join(base, 'willowbrook-mysteries/public/index.html')
    safe_write_file(public_html_path, html_content)

    print(f"✓ Compiled standalone Kindle HTML reader to: {public_html_path}")
    print(f"✓ Successfully generated Chapter {next_chapter_num}: '{new_chapter['title']}' ({new_chapter['wordCount']} words).")

if __name__ == '__main__':
    main()
