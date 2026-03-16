export function HomePage() {
  return (
    <div className="mx-auto w-full max-w-5xl py-8">
      <header className="rounded-xl border border-cyan-400/25 bg-[#081324]/80 px-6 py-10 text-center backdrop-blur-sm">
        <h1 className="text-3xl font-extrabold tracking-tight text-cyan-100 md:text-4xl">
          多模态大模型 RAG 系统
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-cyan-100/70 md:text-base">
          基于先进大模型技术，支持多种模态交互的智能问答系统。
        </p>
      </header>
    </div>
  )
}
