import React from 'react'

const Footer = () => {
  return (
    <footer className="py-4 bg-background">
        <div className="container mx-auto px-4 flex items-center justify-center gap-4 text-muted-foreground text-sm">
          <p>© {new Date().getFullYear()} Creator Connect. All rights reserved.</p>
        </div>
      </footer>
  )
}

export default Footer