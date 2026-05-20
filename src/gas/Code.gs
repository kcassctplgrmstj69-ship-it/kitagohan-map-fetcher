/**
 * kitagohan-map-fetcher
 *
 * Instagram Graph API から @kitagohan_insta の投稿一覧を取得するサンプル。
 *
 * 事前準備:
 *   GAS の「プロジェクトの設定」→「スクリプト プロパティ」に以下を登録
 *     - INSTAGRAM_PAGE_TOKEN: Page Long-Lived Token
 *     - INSTAGRAM_BUSINESS_ACCOUNT_ID: 17841460866415181
 */

const GRAPH_API_VERSION = 'v21.0';

/**
 * Script Properties から設定値を取得（存在チェック付き）
 */
function getConfig_() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('INSTAGRAM_PAGE_TOKEN');
  const igId  = props.getProperty('INSTAGRAM_BUSINESS_ACCOUNT_ID');

  if (!token) {
    throw new Error('Script Property "INSTAGRAM_PAGE_TOKEN" が未設定です');
  }
  if (!igId) {
    throw new Error('Script Property "INSTAGRAM_BUSINESS_ACCOUNT_ID" が未設定です');
  }
  return { token, igId };
}

/**
 * Instagram Graph API を叩く共通ヘルパ
 */
function fetchGraph_(path, params) {
  const { token } = getConfig_();
  const query = Object.entries({ ...params, access_token: token })
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');

  const url = `https://graph.facebook.com/${GRAPH_API_VERSION}/${path}?${query}`;
  const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  const code = res.getResponseCode();
  const body = res.getContentText();

  if (code < 200 || code >= 300) {
    throw new Error(`Graph API error ${code}: ${body}`);
  }
  return JSON.parse(body);
}

/**
 * 最新投稿一覧を取得して Logger に出力
 * メニュー: 実行 → fetchRecentPosts
 */
function fetchRecentPosts() {
  const { igId } = getConfig_();
  const data = fetchGraph_(`${igId}/media`, {
    fields: 'id,caption,media_type,permalink,timestamp,like_count,comments_count,video_play_count',
    limit: 10
  });

  if (!data.data || data.data.length === 0) {
    Logger.log('投稿が見つかりませんでした');
    return [];
  }

  Logger.log(`取得件数: ${data.data.length}`);
  data.data.forEach((post, i) => {
    Logger.log(
      `[${i + 1}] ${post.timestamp} | ` +
      `type=${post.media_type} | ` +
      `likes=${post.like_count ?? '-'} | ` +
      `comments=${post.comments_count ?? '-'} | ` +
      `plays=${post.video_play_count ?? '-'}`
    );
    if (post.caption) {
      Logger.log(`    caption: ${post.caption.substring(0, 60)}...`);
    }
  });
  return data.data;
}

/**
 * Token がまだ有効かを確認
 * メニュー: 実行 → verifyToken
 */
function verifyToken() {
  const { igId } = getConfig_();
  const data = fetchGraph_(igId, { fields: 'id,username,name' });
  Logger.log(`✅ Token 有効`);
  Logger.log(`   IG Business ID: ${data.id}`);
  Logger.log(`   Username: @${data.username}`);
  Logger.log(`   Name: ${data.name}`);
  return data;
}
