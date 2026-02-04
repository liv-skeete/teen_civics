# Threads Integration Strategy for TeenCivics

## 1. Recommendation: Proceed with Threads Integration
Threads offers a significant opportunity for TeenCivics to reach a younger, text-first audience comparable to X (Twitter) and Bluesky. The API is now stable and allows for automated publishing.

## 2. Technical Implementation Plan
Since the Threads API is graph-based (Meta), it differs from the AT Protocol (Bluesky) but shares some structural similarities with Twitter's API.

### Key Components

1.  **Inheritance Structure**:
    -   Create `src/publishers/threads_publisher.py` inheriting from `BasePublisher`.
    -   Implement `format_post()`, `post()`, and `platform_name` property.

2.  **Authentication**:
    -   **Requirement**: Meta Business Account or Creator Account.
    -   **Credentials Needed**: `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN`.
    -   **Token Management**: Threads access tokens are **long-lived (60 days)** and must be refreshed automatically. We will need a utility script or a scheduled task to refresh this token before it expires.

3.  **Posting Logic**:
    -   **Endpoint**: `POST https://graph.threads.net/v1.0/{user_id}/threads`
    -   **Parameters**:
        -   `media_type`: "TEXT"
        -   `text`: The content of the post (Max 500 chars).
    -   **Step 1**: Create a media container.
    -   **Step 2**: Publish the media container.

4.  **Formatting**:
    -   **Character Limit**: 500 characters (providing more breathing room than Bluesky/Twitter).
    -   **Links**: Links are automatically parsed; no facet handling required like in Bluesky.

## 3. Future Considerations: Video Platforms (TikTok / Reels)
While Threads is a direct extension of our current text-based strategy, expanding to video requires a different pipeline.

-   **TikTok/Reels**: Requires **video generation** (not just text).
-   **Automation**: Tools like `moviepy` can generate simple slideshow videos from our bill summaries + images.
-   **Complexity**: High. Requires video rendering, storage, and stricter API compliance (TikTok API is notoriously difficult for purely automated bots without a business relationship).
-   **Recommendation**: Postpone video automation. Focus on Threads as the immediate "easy win" to complete the text-based social triad (Twitter, Bluesky, Threads).

## 4. Next Steps
1.  Register for a Meta Developer account and create a Threads app.
2.  Generate initial Access Token.
3.  Develop `threads_publisher.py`.
4.  Update `publisher_manager.py` to include Threads in the broadcast loop.
