import { BrandMark } from "../components/BrandMark";
import { BLOG_POSTS } from "./posts";

function formatDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function BlogIndex() {
  return (
    <main className="landing-shell blog-shell">
      <header className="landing-nav blog-nav">
        <a className="landing-brand" href="/" aria-label="JunoGuard home">
          <BrandMark className="landing-mark" size={29} />
          <span>JUNOGUARD</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="/#product">Product</a>
          <a href="/#how">How it works</a>
          <a href="/blog" aria-current="page">
            Blog
          </a>
          <a href="/#install">Install</a>
          <a href="https://github.com/cosmicoral/JunoGuard" target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>
        <a className="nav-console" href="/auth/sign-in">
          Live console
        </a>
      </header>

      <section className="blog-index">
        <p className="section-index">FIELD NOTES</p>
        <h1>Blog</h1>
        <p className="blog-index-lede">
          Coding-agent blast radius, install gates, spend controls, and honest
          limits — written so founders and staff engineers can decide with a
          clear head.
        </p>

        <ul className="blog-list">
          {BLOG_POSTS.map((post) => (
            <li key={post.slug}>
              <a className="blog-card" href={`/blog/${post.slug}`}>
                <span className="blog-card-meta">
                  <time dateTime={post.date}>{formatDate(post.date)}</time>
                  <span>{post.readingMinutes} min read</span>
                </span>
                <strong>{post.title}</strong>
                <span className="blog-card-desc">{post.description}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <footer className="landing-footer blog-footer">
        <a className="landing-brand" href="/">
          <BrandMark className="landing-mark" size={29} />
          <span>JUNOGUARD</span>
        </a>
        <p>The supervision layer for AI coding agents.</p>
        <span>BUILT IN LONDON · 2026</span>
      </footer>
    </main>
  );
}
