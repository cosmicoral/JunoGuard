import { BrandMark } from "../components/BrandMark";
import { IconArrowRight } from "../components/Icons";
import { renderMarkdown } from "./Markdown";
import { BLOG_POSTS, getPost } from "./posts";

function formatDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function BlogPost({ slug }: { slug: string }) {
  const post = getPost(slug);

  if (!post) {
    return (
      <main className="landing-shell blog-shell">
        <header className="landing-nav blog-nav">
          <a className="landing-brand" href="/" aria-label="JunoGuard home">
            <BrandMark className="landing-mark" size={29} />
            <span>JUNOGUARD</span>
          </a>
          <a className="nav-console" href="/blog">
            All posts
          </a>
        </header>
        <section className="blog-article">
          <h1>Post not found</h1>
          <p>
            That field note does not exist.{" "}
            <a href="/blog">Back to the blog</a>.
          </p>
        </section>
      </main>
    );
  }

  // Drop the leading H1 from the markdown body — the page chrome already renders it.
  const body = post.body.replace(/^#\s+.+\n+/, "");
  const others = BLOG_POSTS.filter((p) => p.slug !== post.slug).slice(0, 3);

  return (
    <main className="landing-shell blog-shell">
      <header className="landing-nav blog-nav">
        <a className="landing-brand" href="/" aria-label="JunoGuard home">
          <BrandMark className="landing-mark" size={29} />
          <span>JUNOGUARD</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="/#product">Product</a>
          <a href="/blog">Blog</a>
          <a href="/#install">Install</a>
        </nav>
        <a className="nav-console" href="/auth/sign-in">
          Live console
        </a>
      </header>

      <article className="blog-article">
        <p className="section-index">FIELD NOTES</p>
        <h1>{post.title}</h1>
        <div className="blog-article-meta">
          <time dateTime={post.date}>{formatDate(post.date)}</time>
          <span>{post.readingMinutes} min read</span>
          <span>{post.keyword}</span>
        </div>

        <div className="blog-prose">{renderMarkdown(body)}</div>

        <aside className="blog-cta">
          <p>Keep the agent productive — without the blast radius.</p>
          <div>
            <a className="primary-action" href="/">
              Visit junoguard.com <IconArrowRight size={14} />
            </a>
            <code className="blog-cta-cmd">npx @heysalad/junoguard init</code>
          </div>
        </aside>
      </article>

      {others.length > 0 && (
        <section className="blog-more">
          <p className="section-index">MORE FIELD NOTES</p>
          <ul className="blog-list">
            {others.map((item) => (
              <li key={item.slug}>
                <a className="blog-card" href={`/blog/${item.slug}`}>
                  <strong>{item.title}</strong>
                  <span className="blog-card-desc">{item.description}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="landing-footer blog-footer">
        <a className="landing-brand" href="/">
          <BrandMark className="landing-mark" size={29} />
          <span>JUNOGUARD</span>
        </a>
        <p>
          <a href="/blog">All posts</a>
        </p>
        <span>BUILT IN LONDON · 2026</span>
      </footer>
    </main>
  );
}
