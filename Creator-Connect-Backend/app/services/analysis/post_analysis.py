import json
import logging
from typing import Dict, List, Any
from collections import Counter
from datetime import datetime

from app.services.legacy.brightdata import BRIGHTDATA_POST_FIELDS, normalize_posts_for_display

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (single BrightData source: app.services.legacy.brightdata)
__all__ = ["BRIGHTDATA_POST_FIELDS", "normalize_posts_for_display", "POST_DISPLAY_KEYS"]

POST_DISPLAY_KEYS = ("image_url", "caption", "likes", "comments", "content_type", "post_hashtags", "permalink")


def extract_hashtags_from_posts(posts: List[Dict]) -> Dict:
    """
    Extract and analyze hashtags from post data.
    Returns hashtag frequency, effectiveness, and recommendations.
    """
    if posts is None or not posts:
        return {
            'total_unique_hashtags': 0,
            'most_used_hashtags': [],
            'best_performing_hashtags': [],
            'avg_hashtags_per_post': 0
        }

    all_hashtags = []
    hashtag_engagement = {}

    for post in posts:
        if not post:
            continue
        hashtags = post.get('post_hashtags') or []
        likes = post.get('likes') or 0
        comments = post.get('comments') or 0
        engagement = likes + comments

        for tag in hashtags:
            if not tag or not isinstance(tag, str):
                continue
            if not tag.startswith('#'):
                tag = f"#{tag}"

            all_hashtags.append(tag)
            if tag not in hashtag_engagement:
                hashtag_engagement[tag] = {'total_engagement': 0, 'count': 0}
            hashtag_engagement[tag]['total_engagement'] += engagement
            hashtag_engagement[tag]['count'] += 1

    if not all_hashtags:
        return {
            'total_unique_hashtags': 0,
            'most_used_hashtags': [],
            'best_performing_hashtags': [],
            'avg_hashtags_per_post': 0
        }

    hashtag_avg_engagement = {}
    for tag, data in hashtag_engagement.items():
        hashtag_avg_engagement[tag] = data['total_engagement'] / data['count']

    hashtag_counts = Counter(all_hashtags)
    most_used = hashtag_counts.most_common(10)

    best_performing = sorted(
        hashtag_avg_engagement.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    return {
        'total_unique_hashtags': len(hashtag_counts),
        'most_used_hashtags': [{'tag': tag, 'count': count} for tag, count in most_used],
        'best_performing_hashtags': [{'tag': tag, 'avg_engagement': int(eng)} for tag, eng in best_performing],
        'avg_hashtags_per_post': round(len(all_hashtags) / len(posts), 1) if posts else 0
    }


def analyze_posts_with_llm(result: Dict, gemini_client) -> Dict:
    """
    🤖 LLM-POWERED POST ANALYSIS
    Analyzes recent posts to provide deep insights about content strategy.
    """
    from app.prompts import POST_ANALYSIS_SYSTEM, POST_ANALYSIS_USER_TEMPLATE
    from app.config.settings import settings

    posts = result.get('posts') or []
    if not posts or len(posts) == 0:
        logger.debug(f"No posts available for {result.get('NAME')}, skipping post analysis")
        return {
            'post_analysis_available': False,
            'reason': 'No posts data available'
        }

    recent_posts = posts[:12]

    posts_summary = []
    for i, post in enumerate(recent_posts, 1):
        caption_preview = (post.get('caption', 'No caption')[:100] + '...') if len(post.get('caption', '')) > 100 else post.get('caption', 'No caption')
        posts_summary.append(
            f"Post {i}: {post.get('content_type', 'Unknown')} | "
            f"Likes: {post.get('likes', 0):,} | Comments: {post.get('comments', 0)} | "
            f"Hashtags: {len(post.get('post_hashtags', []))} | "
            f"Caption: \"{caption_preview}\""
        )

    posts_data = "\n".join(posts_summary)

    username = result.get('Id', result.get('username', 'unknown'))
    niche = result.get('NICHE', 'Digital Creator')
    followers = result.get('followers', 'N/A')

    prompt = POST_ANALYSIS_USER_TEMPLATE.format(
        username=username,
        niche=niche,
        followers=followers,
        post_count=len(recent_posts),
        posts_data=posts_data
    )

    try:
        full_prompt = f"{POST_ANALYSIS_SYSTEM}\n\n{prompt}"
        response = gemini_client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=full_prompt,
            config={"temperature": 0.3, "response_mime_type": "application/json"}
        )

        response_text = response.text.strip()
        analysis = json.loads(response_text)

        logger.debug(f"Post analysis: @{username}")

        return {
            'post_analysis_available': True,
            **analysis
        }

    except Exception as e:
        logger.warning(f"   ⚠️ Post analysis failed for @{username}: {e}")
        return {
            'post_analysis_available': False,
            'reason': f'Analysis failed: {str(e)}'
        }


def add_post_metrics_to_result(result: Dict, gemini_client=None) -> Dict:
    """
    Add post analysis and hashtag metrics to influencer result.
    This enhances the result with deep insights from post data.
    """
    posts = result.get('posts', [])

    if posts:
        hashtag_analysis = extract_hashtags_from_posts(posts)
        result['hashtag_analysis'] = hashtag_analysis

        if hashtag_analysis['most_used_hashtags']:
            result['top_hashtags'] = [h['tag'] for h in hashtag_analysis['most_used_hashtags'][:5]]
        else:
            result['top_hashtags'] = []

        if gemini_client:
            post_analysis = analyze_posts_with_llm(result, gemini_client)
            result['post_analysis'] = post_analysis
        else:
            result['post_analysis'] = {
                'post_analysis_available': False,
                'reason': 'LLM client not provided'
            }

    else:
        result['hashtag_analysis'] = {
            'total_unique_hashtags': 0,
            'most_used_hashtags': [],
            'best_performing_hashtags': [],
            'avg_hashtags_per_post': 0
        }
        result['top_hashtags'] = []
        result['post_analysis'] = {
            'post_analysis_available': False,
            'reason': 'No posts data'
        }

    return result
