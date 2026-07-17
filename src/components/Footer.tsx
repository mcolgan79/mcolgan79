/**
 * Site footer: legal links (served as static pages in public/) plus the
 * standing not-advice line. Links open in a new tab so the app keeps its state.
 */
export function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer className="app-footer">
      <nav className="footer-links" aria-label="Legal">
        <a href="./terms.html" target="_blank" rel="noopener noreferrer">
          Terms
        </a>
        <a href="./privacy.html" target="_blank" rel="noopener noreferrer">
          Privacy
        </a>
        <a href="./refunds.html" target="_blank" rel="noopener noreferrer">
          Refunds
        </a>
        <a href="mailto:michael.colgan@gmail.com">Contact</a>
      </nav>
      <p className="footer-legal">
        © {year} Pera Pera, Inc. · OptPoP is for education and analysis only — not
        investment advice.
      </p>
    </footer>
  )
}
