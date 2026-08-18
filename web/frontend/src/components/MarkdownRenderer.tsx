import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeRaw from 'rehype-raw';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import 'katex/dist/katex.min.css';

interface Props {
  content: string;
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <div className="md-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeKatex]}
        components={{
          code({ node, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const codeText = String(children).replace(/\n$/, '');
            const inline = !match && !codeText.includes('\n');
            if (!inline) {
              // 未指名语言的代码块按纯文本（txt）解析
              const language = match ? match[1] : 'text';
              const label = match ? match[1] : 'txt';
              return (
                <div className="rounded-lg overflow-hidden my-3 border border-gray-200 dark:border-gray-700">
                  <div className="px-4 py-1.5 bg-gray-100 dark:bg-gray-800 text-[10px] text-gray-500 dark:text-gray-400 font-mono">
                    {label}
                  </div>
                  <SyntaxHighlighter
                    style={oneDark}
                    language={language}
                    PreTag="div"
                    customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.75rem' }}
                  >
                    {codeText}
                  </SyntaxHighlighter>
                </div>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          img({ src, alt }) {
            return (
              <img
                src={src || ''}
                alt={alt || ''}
                className="rounded-lg max-w-full"
                loading="lazy"
              />
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
