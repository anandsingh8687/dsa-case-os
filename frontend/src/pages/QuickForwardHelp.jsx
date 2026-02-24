import React from 'react';
import { MessageCircle, FileUp, CheckCircle2 } from 'lucide-react';
import { Card } from '../components/ui';

const QuickForwardHelp = () => {
  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Quick Forward Help</h1>
        <p className="text-sm text-gray-600 mt-2">
          Forward borrower chats and files directly to WhatsApp number <span className="font-semibold">8130781881</span>.
          The system auto-creates/updates case and starts document processing.
        </p>
      </div>

      <Card>
        <div className="flex items-start gap-3">
          <MessageCircle className="w-5 h-5 text-primary mt-1" />
          <div>
            <h2 className="font-semibold text-gray-900">Step 1: Start message with hint</h2>
            <p className="text-sm text-gray-700 mt-1">
              First line should include one strong identifier: <span className="font-medium">CASE ID</span>,
              <span className="font-medium"> PAN</span>, or borrower name.
            </p>
            <pre className="mt-3 rounded bg-gray-50 p-3 text-xs text-gray-700 overflow-x-auto">{`CASE-20260223-0001
Please update with latest GST and bank statement.`}</pre>
          </div>
        </div>
      </Card>

      <Card>
        <div className="flex items-start gap-3">
          <FileUp className="w-5 h-5 text-primary mt-1" />
          <div>
            <h2 className="font-semibold text-gray-900">Step 2: Forward documents</h2>
            <p className="text-sm text-gray-700 mt-1">
              Forward PDF/image documents in the same thread. Supported: GST docs, bank statements, KYC docs, CIBIL.
            </p>
            <ul className="mt-3 list-disc pl-5 text-sm text-gray-700 space-y-1">
              <li>Use clear file names where possible.</li>
              <li>If this is a fresh case, send <code>/newcase</code> first.</li>
              <li>To force update on existing case, send <code>/update CASE-YYYYMMDD-XXXX</code>.</li>
            </ul>
          </div>
        </div>
      </Card>

      <Card>
        <div className="flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-green-600 mt-1" />
          <div>
            <h2 className="font-semibold text-gray-900">Step 3: Track command responses</h2>
            <p className="text-sm text-gray-700 mt-1">Use commands in WhatsApp:</p>
            <ul className="mt-2 list-disc pl-5 text-sm text-gray-700 space-y-1">
              <li><code>/newcase</code> create fresh case</li>
              <li><code>/status CASE-YYYYMMDD-XXXX</code> check processing status</li>
              <li><code>/report CASE-YYYYMMDD-XXXX</code> get report snapshot</li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default QuickForwardHelp;
