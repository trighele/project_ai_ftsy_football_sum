# Fantasy Football Podcast Summarizer

Turns a fantasy football podcast episode on YouTube into a structured Markdown summary, using current NFL player data so that player mentions are attributed to the right team, position, and standing.

## Language

### Episode material

**Captions**:
The timed text track YouTube holds for a video, either uploaded by the channel or machine-generated. The raw source material we retrieve.
_Avoid_: subtitles, CC

**Transcript**:
The plain running text of an episode, derived from its captions. What Claude is given to summarize.
_Avoid_: transcription

**Episode**:
A single podcast instalment identified by its YouTube URL, carrying a title, channel, and upload date.
_Avoid_: video, podcast

**Summary**:
The structured Markdown write-up Claude produces from a transcript — news items with sentiment, matchup analysis, player debates, waiver suggestions.

**Run**:
One end-to-end pass over an episode: fetch captions, build the transcript, summarize. Runs are saved and can be reopened later.
_Avoid_: job, task, session

### Player data

**Player reference**:
The set of current NFL players we hand to Claude so it can attribute a name to the right team and position. A deliberately narrowed slice of the full player table.
_Avoid_: player table, roster

**Depth rank**:
A player's position on their team's depth chart — 1 for the starter, 2 for the primary backup, and so on. Says who is on the field, not who is good.
_Avoid_: tier, string, depth chart position

**ECR tier**:
A player's fantasy-value grouping from expert consensus rankings. Says who is worth starting, independent of depth chart position.
_Avoid_: tier, rank

> **Depth rank and ECR tier are different things and must never be collapsed into a single "tier".** A team's starting kicker is depth rank 1 and a bottom ECR tier; a rookie in a committee backfield can be depth rank 2 and a high ECR tier. Both are carried, both are named explicitly.

**Season**:
The NFL season year a set of player data belongs to. Player data is always read as of a specific season, and the season in use is always shown.

**Sync**:
Refreshing the locally cached player reference from the upstream nflverse data. Happens automatically when the cache is stale and on demand from the Players page.
_Avoid_: refresh, update, pull
