import Image from "next/image";
import Link from "next/link";

import logo from "@/assets/logo.svg";
import productScreenshot from "@/assets/product_screenshot.png";

export default function Home() {
  return (
    <main className="min-h-screen bg-[#111111] text-white">
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-16 px-6 pb-10 pt-12 md:px-10">
        <header className="motion-page-enter grid grid-cols-[auto_1fr_auto] items-center gap-6">
          <Link
            href="/"
            aria-label="Mistral Home"
            className="motion-interactive flex w-[110px] justify-start"
          >
            <span className="flex h-10 w-10 items-center justify-start">
              <Image src={logo} alt="Mistral logo" priority />
            </span>
          </Link>

          <nav className="hidden items-center justify-center gap-6 text-sm font-medium text-white md:flex">
            <Link href="#" className="motion-link hover:opacity-80">
              Platform
            </Link>
            <Link href="#" className="motion-link hover:opacity-80">
              How It Works
            </Link>
            <Link href="#" className="motion-link hover:opacity-80">
              Use Cases
            </Link>
            <Link href="#" className="motion-link hover:opacity-80">
              Docs
            </Link>
          </nav>

          <div className="flex items-center gap-6 text-sm font-medium">
            <Link href="#" className="motion-link hover:opacity-80">
              Login
            </Link>
            <Link href="#" className="motion-link hover:opacity-80">
              Sign up
            </Link>
          </div>
        </header>

        <section className="motion-page-enter motion-delay-1 flex flex-col gap-6">
          <div className="max-w-[566px] motion-page-enter motion-delay-2">
            <h1 className="text-balance text-[48px] font-light leading-[1.2] tracking-[-0.02em] md:text-[48px]">
              Keep your models close,
              <br />
              Keep your adversaries closer.
            </h1>
            <p className="mt-4 text-base leading-6 text-[#aaaaaa]">
              Our adversarial agents discover real-world failure modes in vision
              models by applying physically plausible image edits to stress-test
              detection, classification, and segmentation. Measure model
              degradation, ship evidence-backed improvements, and build truly
              robust systems.
            </p>

            <div className="mt-8 flex items-center gap-6">
              <Link
                href="/dashboard/projects"
                className="motion-interactive inline-flex min-h-9 items-center justify-center rounded-[8px] bg-white px-4 py-2 text-sm font-medium text-[#171717]"
              >
                Get Started
              </Link>
              <Link href="#" className="motion-link text-base font-medium text-white hover:opacity-80">
                Watch demo
              </Link>
            </div>
          </div>
          <Image
            src={productScreenshot}
            alt="Mistral adversarial dashboard screenshot"
            priority
            className="motion-image motion-page-enter motion-delay-3 h-auto w-full"
          />
        </section>
      </div>

      <footer className="motion-page-enter motion-delay-2 mt-20 bg-[#1A1A1A]">
        <div className="mx-auto w-full max-w-[1200px] px-6 py-14 md:px-10 md:py-16">
          <div className="grid grid-cols-2 gap-x-10 gap-y-10 md:grid-cols-4 md:gap-x-16">
            <div className="space-y-3">
              <p className="text-sm text-[#8f8f8f]">Explore</p>
              <div className="flex flex-col gap-2 text-base leading-7 text-[#efefef]">
                <Link href="#" className="motion-link hover:opacity-80">Overview</Link>
                <Link href="#" className="motion-link hover:opacity-80">How It Works</Link>
                <Link href="#" className="motion-link hover:opacity-80">Request Demo</Link>
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-sm text-[#8f8f8f]">Resources</p>
              <div className="flex flex-col gap-2 text-base leading-7 text-[#efefef]">
                <Link href="#" className="motion-link hover:opacity-80">Guides</Link>
                <Link href="#" className="motion-link hover:opacity-80">API Reference</Link>
                <Link href="#" className="motion-link hover:opacity-80">Release Notes</Link>
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-sm text-[#8f8f8f]">Company</p>
              <div className="flex flex-col gap-2 text-base leading-7 text-[#efefef]">
                <Link href="#" className="motion-link hover:opacity-80">About</Link>
                <Link href="#" className="motion-link hover:opacity-80">Careers</Link>
                <Link href="#" className="motion-link hover:opacity-80">Contact</Link>
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-sm text-[#8f8f8f]">Connect</p>
              <div className="flex flex-col gap-2 text-base leading-7 text-[#efefef]">
                <Link href="#" className="motion-link hover:opacity-80">X</Link>
                <Link href="#" className="motion-link hover:opacity-80">GitHub</Link>
                <Link href="#" className="motion-link hover:opacity-80">YouTube</Link>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}
