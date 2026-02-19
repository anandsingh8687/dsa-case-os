import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Send, Bot, User, RotateCcw, Brain } from 'lucide-react';
import { queryCopilot } from '../api/services';
import { Card, Button } from '../components/ui';
import { getUser } from '../utils/auth';

const MAX_LOCAL_HISTORY = 40;

const toStorageKey = (email) => `credilo_copilot_history_v2_${email || 'anonymous'}`;

const renderInlineBold = (line, prefix) => {
  const parts = String(line).split(/\*\*(.*?)\*\*/g);
  return parts.map((part, idx) =>
    idx % 2 === 1 ? (
      <strong key={`${prefix}-b-${idx}`}>{part}</strong>
    ) : (
      <span key={`${prefix}-t-${idx}`}>{part}</span>
    )
  );
};

const renderFormattedMessage = (content, idPrefix = 'msg') => {
  const normalized = String(content || '').replace(/\r\n/g, '\n').replace(/\\n/g, '\n');
  const lines = normalized.split('\n');
  return (
    <div className="space-y-1">
      {lines.map((rawLine, lineIdx) => {
        const line = rawLine.trim();
        if (!line) {
          return <div key={`${idPrefix}-empty-${lineIdx}`} className="h-1.5" />;
        }
        if (/^#{1,3}\s+/.test(line)) {
          return (
            <div key={`${idPrefix}-h-${lineIdx}`} className="font-semibold text-sm">
              {renderInlineBold(line.replace(/^#{1,3}\s+/, ''), `${idPrefix}-h-${lineIdx}`)}
            </div>
          );
        }
        if (/^[-*•]\s+/.test(line)) {
          return (
            <div key={`${idPrefix}-li-${lineIdx}`} className="text-sm flex gap-2">
              <span className="mt-[2px]">•</span>
              <span>{renderInlineBold(line.replace(/^[-*•]\s+/, ''), `${idPrefix}-li-${lineIdx}`)}</span>
            </div>
          );
        }
        if (/^\d+\.\s+/.test(line)) {
          const marker = line.match(/^\d+\./)?.[0] || '';
          return (
            <div key={`${idPrefix}-ol-${lineIdx}`} className="text-sm flex gap-2">
              <span>{marker}</span>
              <span>{renderInlineBold(line.replace(/^\d+\.\s+/, ''), `${idPrefix}-ol-${lineIdx}`)}</span>
            </div>
          );
        }
        return (
          <p key={`${idPrefix}-p-${lineIdx}`} className="text-sm leading-relaxed">
            {renderInlineBold(line, `${idPrefix}-p-${lineIdx}`)}
          </p>
        );
      })}
    </div>
  );
};

const Copilot = () => {
  const user = useMemo(() => getUser(), []);
  const storageKey = useMemo(() => toStorageKey(user?.email), [user?.email]);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (!stored) return;
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed)) {
        setMessages(parsed.slice(-MAX_LOCAL_HISTORY));
      }
    } catch {
      setMessages([]);
    }
  }, [storageKey]);

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(messages.slice(-MAX_LOCAL_HISTORY)));
  }, [messages, storageKey]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const queryMutation = useMutation({
    mutationFn: queryCopilot,
    onSuccess: (response) => {
      const assistantReply =
        response?.data?.answer ||
        response?.data?.response ||
        'I could not generate a response. Please try rephrasing your query.';

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: assistantReply,
          sources: Array.isArray(response?.data?.sources) ? response.data.sources.slice(0, 5) : [],
          ts: Date.now(),
        },
      ]);
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
          ts: Date.now(),
        },
      ]);
    },
  });

  const handleSend = (forcedText = null) => {
    const outbound = (forcedText ?? input).trim();
    if (!outbound) return;

    const userMessage = { role: 'user', content: outbound, ts: Date.now() };
    setMessages((prev) => [...prev, userMessage]);
    if (!forcedText) {
      setInput('');
    }

    const history = messages.slice(-12).map((item) => ({
      role: item.role,
      content: item.content,
    }));
    queryMutation.mutate({
      query: outbound,
      history,
    });
  };

  const suggestions = [
    'Low CIBIL lenders',
    'Lenders in Mumbai',
    'Compare Bajaj vs IIFL',
    'No Video KYC lenders',
  ];

  const handleSuggestionClick = (suggestion) => {
    handleSend(suggestion);
  };

  const clearThread = () => {
    setMessages([]);
    localStorage.removeItem(storageKey);
  };

  return (
    <div className="max-w-4xl mx-auto h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">Copilot</h1>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-3 py-1 text-xs text-blue-800 border border-blue-100">
            <Brain className="w-3.5 h-3.5" />
            Memory active
          </span>
          <Button size="sm" variant="outline" onClick={clearThread}>
            <span className="inline-flex items-center gap-1">
              <RotateCcw className="w-3.5 h-3.5" />
              Clear Thread
            </span>
          </Button>
        </div>
      </div>

      <Card className="flex-1 flex flex-col h-[calc(100vh-12rem)]">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="text-center py-12">
              <Bot className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-gray-700 mb-2">
                How can I help you today?
              </h3>
              <p className="text-gray-500 mb-6">
                Ask me about lenders, policies, or case recommendations.
              </p>

              {/* Suggestions */}
              <div className="flex flex-wrap gap-2 justify-center">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => handleSuggestionClick(suggestion)}
                    className="px-4 py-2 bg-blue-50 text-primary rounded-full text-sm hover:bg-blue-100 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <div
                key={`${message.role}-${index}-${message.ts || index}`}
                className={`flex items-start gap-3 ${
                  message.role === 'user' ? 'justify-end' : ''
                }`}
              >
                {message.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                    <Bot className="w-5 h-5 text-white" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-lg p-4 ${
                    message.role === 'user'
                      ? 'bg-primary text-white'
                      : 'bg-gray-100 text-gray-900 border border-gray-200'
                  }`}
                >
                  {renderFormattedMessage(message.content, `msg-${index}`)}
                  {Array.isArray(message.sources) && message.sources.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {message.sources.map((source, sourceIdx) => (
                        <span
                          key={`source-${index}-${sourceIdx}`}
                          className="text-[11px] bg-white border border-gray-200 rounded-full px-2 py-0.5 text-gray-600"
                        >
                          {source.lender_name || 'Source'}{source.product_name ? ` • ${source.product_name}` : ''}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {message.role === 'user' && (
                  <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center flex-shrink-0">
                    <User className="w-5 h-5 text-gray-600" />
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />

          {queryMutation.isPending && (
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <div className="bg-gray-100 rounded-lg p-4">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <div
                    className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: '0.1s' }}
                  />
                  <div
                    className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: '0.2s' }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t p-4">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              rows={2}
              placeholder="Ask me anything... (Enter to send, Shift+Enter for new line)"
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || queryMutation.isPending}
              className="flex items-center gap-2"
            >
              <Send className="w-4 h-4" />
              Send
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default Copilot;
