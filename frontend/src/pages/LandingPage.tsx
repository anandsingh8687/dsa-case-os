import React from 'react';
import { motion } from 'framer-motion';
import {
  ArrowRight,
  CheckCircle,
  Brain,
  FileText,
  TrendingUp,
  Zap,
  Users,
  Shield,
  Clock,
  Target
} from 'lucide-react';
import crediloLogo from '../assets/credilo-logo.svg';

const LOGIN_URL = '/login';

const LandingPage = () => {
  const scrollToHowItWorks = () => {
    const section = document.getElementById('how-it-works');
    if (section) {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const features = [
    {
      icon: <Brain className="w-6 h-6" />,
      title: "AI-Powered Intelligence",
      description: "Advanced AI analyzes documents and matches borrowers with the best lenders instantly"
    },
    {
      icon: <Zap className="w-6 h-6" />,
      title: "Lightning Fast Processing",
      description: "Process loan cases in minutes, not days. Auto-extract data from 20+ document types"
    },
    {
      icon: <Target className="w-6 h-6" />,
      title: "Smart Lender Matching",
      description: "Access 18+ NBFCs with 24 products. Get instant eligibility across all lenders"
    },
    {
      icon: <Shield className="w-6 h-6" />,
      title: "Bank-Grade Security",
      description: "Enterprise-level encryption. Your data is safe and compliant"
    }
  ];

  const howItWorks = [
    {
      step: 1,
      title: "Upload Documents",
      description: "Simply upload borrower documents - bank statements, GST returns, KYC, CIBIL reports",
      icon: <FileText className="w-8 h-8" />,
      color: "bg-blue-500"
    },
    {
      step: 2,
      title: "AI Extracts Data",
      description: "Our AI automatically reads, classifies, and extracts all critical information",
      icon: <Brain className="w-8 h-8" />,
      color: "bg-purple-500"
    },
    {
      step: 3,
      title: "Instant Matching",
      description: "Get matched with eligible lenders in seconds. See scores, probabilities, and ticket sizes",
      icon: <Target className="w-8 h-8" />,
      color: "bg-green-500"
    },
    {
      step: 4,
      title: "Generate Report",
      description: "Get a comprehensive case intelligence report ready to submit",
      icon: <TrendingUp className="w-8 h-8" />,
      color: "bg-orange-500"
    }
  ];

  const stats = [
    { number: "18+", label: "NBFC Partners", icon: <Users /> },
    { number: "< 5min", label: "Avg. Processing Time", icon: <Clock /> },
    { number: "24", label: "Loan Products", icon: <FileText /> },
    { number: "95%", label: "Accuracy Rate", icon: <CheckCircle /> }
  ];

  const benefits = [
    "✓ Save 80% time on data entry",
    "✓ Zero manual document reading",
    "✓ Instant lender eligibility check",
    "✓ Professional case reports",
    "✓ AI copilot for lender queries",
    "✓ Track all cases in one dashboard"
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        {/* Background Pattern */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-500 rounded-full filter blur-3xl" />
          <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500 rounded-full filter blur-3xl" />
        </div>

        {/* Navigation */}
        <nav className="relative z-10 container mx-auto px-6 py-6 flex justify-between items-center">
          <div className="flex items-center space-x-2">
            <img
              src={crediloLogo}
              alt="Credilo logo"
              className="w-10 h-10 rounded-lg object-cover border border-white/20"
            />
            <span className="text-2xl font-bold text-white">Credilo</span>
          </div>
          <div className="flex space-x-4">
            <button
              onClick={() => window.location.href = '/pincode-checker'}
              className="px-6 py-2 text-white hover:text-blue-300 transition"
            >
              Pincode Checker
            </button>
            <button
              onClick={() => window.location.href = LOGIN_URL}
              className="px-6 py-2 text-white hover:text-blue-300 transition"
            >
              Sign In
            </button>
            <button
              onClick={() => window.location.href = LOGIN_URL}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
            >
              Get Started
            </button>
          </div>
        </nav>

        {/* Hero Content */}
        <div className="relative z-10 container mx-auto px-6 py-20">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <motion.div
              initial={{ opacity: 0, x: -50 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8 }}
            >
              <h1 className="text-5xl md:text-6xl font-bold text-white leading-tight mb-6">
                AI-Powered Credit Intelligence for
                <span className="text-blue-400"> Business Loans</span>
              </h1>
              <p className="text-xl text-gray-300 mb-8">
                Transform borrower documents into lender-ready cases in minutes.
                Smart matching, instant eligibility, zero manual work.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 mb-8">
                <button
                  onClick={() => window.location.href = LOGIN_URL}
                  className="px-8 py-4 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition flex items-center justify-center space-x-2"
                >
                  <span>Start Free Trial</span>
                  <ArrowRight className="w-5 h-5" />
                </button>
                <button
                  onClick={scrollToHowItWorks}
                  className="px-8 py-4 bg-white/10 text-white rounded-lg font-semibold hover:bg-white/20 transition backdrop-blur"
                >
                  See How It Works
                </button>
              </div>
              <div className="grid grid-cols-3 gap-4 text-white">
                {benefits.slice(0, 3).map((benefit, i) => (
                  <div key={i} className="flex items-center space-x-2">
                    <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
                    <span className="text-sm">{benefit.replace('✓ ', '')}</span>
                  </div>
                ))}
              </div>
            </motion.div>

            {/* Hero Visual - Dashboard Preview */}
            <motion.div
              initial={{ opacity: 0, y: 50 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              className="relative"
            >
              <div className="bg-white/10 backdrop-blur-xl rounded-2xl border border-white/20 p-8 shadow-2xl">
                <div className="flex items-center justify-between mb-6">
                  <span className="text-white font-semibold">Live Demo</span>
                  <div className="flex space-x-2">
                    <div className="w-3 h-3 bg-red-500 rounded-full" />
                    <div className="w-3 h-3 bg-yellow-500 rounded-full" />
                    <div className="w-3 h-3 bg-green-500 rounded-full" />
                  </div>
                </div>

                {/* Simulated Dashboard */}
                <div className="space-y-4">
                  <div className="bg-gradient-to-r from-blue-500/20 to-purple-500/20 p-4 rounded-lg border border-blue-400/30">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-white text-sm">Case Processing</span>
                      <span className="text-green-400 text-sm font-bold">95% Complete</span>
                    </div>
                    <div className="w-full bg-white/20 rounded-full h-2">
                      <motion.div
                        className="bg-gradient-to-r from-blue-500 to-green-500 h-2 rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: "95%" }}
                        transition={{ duration: 2, ease: "easeOut" }}
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-white/5 p-3 rounded-lg border border-white/10">
                      <div className="text-gray-400 text-xs mb-1">Documents</div>
                      <div className="text-white text-2xl font-bold">23</div>
                    </div>
                    <div className="bg-white/5 p-3 rounded-lg border border-white/10">
                      <div className="text-gray-400 text-xs mb-1">Matched Lenders</div>
                      <div className="text-green-400 text-2xl font-bold">4</div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {['Bank Statement', 'GST Returns', 'CIBIL Report', 'PAN Card'].map((doc, i) => (
                      <motion.div
                        key={i}
                        className="flex items-center justify-between bg-white/5 p-2 rounded border border-white/10"
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.5 + i * 0.1 }}
                      >
                        <span className="text-white text-sm">{doc}</span>
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      </motion.div>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </div>

      {/* Stats Section */}
      <div className="relative z-10 container mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((stat, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="bg-white/10 backdrop-blur-xl rounded-xl p-6 border border-white/20 text-center"
            >
              <div className="flex justify-center mb-3 text-blue-400">
                {stat.icon}
              </div>
              <div className="text-4xl font-bold text-white mb-2">{stat.number}</div>
              <div className="text-gray-300">{stat.label}</div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* How It Works */}
      <div id="how-it-works" className="relative z-10 container mx-auto px-6 py-20">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold text-white mb-4">How It Works</h2>
          <p className="text-xl text-gray-300">From documents to decision in 4 simple steps</p>
        </div>

        <div className="grid md:grid-cols-4 gap-8">
          {howItWorks.map((step, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.2 }}
              className="relative"
            >
              {/* Connection Line */}
              {i < howItWorks.length - 1 && (
                <div className="hidden md:block absolute top-16 left-1/2 w-full h-0.5 bg-gradient-to-r from-blue-500/50 to-purple-500/50" />
              )}

              <div className="relative bg-white/10 backdrop-blur-xl rounded-xl p-6 border border-white/20 hover:border-blue-400/50 transition">
                <div className={`${step.color} w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-white`}>
                  {step.icon}
                </div>
                <div className="absolute top-4 right-4 text-white/20 text-4xl font-bold">{step.step}</div>
                <h3 className="text-xl font-semibold text-white mb-2 text-center">{step.title}</h3>
                <p className="text-gray-300 text-center">{step.description}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Features Grid */}
      <div className="relative z-10 container mx-auto px-6 py-20">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold text-white mb-4">Powerful Features</h2>
          <p className="text-xl text-gray-300">Everything you need to process business loan cases</p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.9 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="bg-white/10 backdrop-blur-xl rounded-xl p-6 border border-white/20 hover:border-blue-400/50 transition group"
            >
              <div className="text-blue-400 mb-4 group-hover:scale-110 transition">
                {feature.icon}
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">{feature.title}</h3>
              <p className="text-gray-300 text-sm">{feature.description}</p>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Benefits Section */}
      <div className="relative z-10 container mx-auto px-6 py-20">
        <div className="bg-gradient-to-r from-blue-600/20 to-purple-600/20 rounded-3xl p-12 border border-blue-400/30 backdrop-blur-xl">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="text-4xl font-bold text-white mb-6">Why DSAs Love Us</h2>
              <div className="space-y-4">
                {benefits.map((benefit, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1 }}
                    className="flex items-center space-x-3"
                  >
                    <CheckCircle className="w-6 h-6 text-green-400 flex-shrink-0" />
                    <span className="text-lg text-white">{benefit.replace('✓ ', '')}</span>
                  </motion.div>
                ))}
              </div>
            </div>

            <div className="bg-white/5 rounded-2xl p-8 border border-white/10">
              <div className="text-center mb-6">
                <div className="text-6xl font-bold text-white mb-2">80%</div>
                <div className="text-xl text-gray-300">Time Saved</div>
              </div>
              <p className="text-gray-300 text-center mb-6">
                "Credilo transformed our workflow. What used to take 2 hours now takes 10 minutes.
                The AI is incredibly accurate!"
              </p>
              <div className="flex items-center justify-center space-x-3">
                <div className="w-12 h-12 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white font-bold">
                  RK
                </div>
                <div>
                  <div className="text-white font-semibold">Rajesh Kumar</div>
                  <div className="text-gray-400 text-sm">Senior DSA, Mumbai</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="relative z-10 container mx-auto px-6 py-20">
        <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-3xl p-12 text-center">
          <h2 className="text-4xl font-bold text-white mb-4">Ready to Transform Your Workflow?</h2>
          <p className="text-xl text-white/90 mb-8">Join hundreds of DSAs already using Credilo</p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={() => window.location.href = LOGIN_URL}
              className="px-10 py-4 bg-white text-blue-600 rounded-lg font-bold text-lg hover:bg-gray-100 transition"
            >
              Start Free Trial
            </button>
            <button
              onClick={() => window.location.href = LOGIN_URL}
              className="px-10 py-4 bg-white/20 text-white rounded-lg font-bold text-lg hover:bg-white/30 transition backdrop-blur"
            >
              Sign In
            </button>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="relative z-10 container mx-auto px-6 py-8 border-t border-white/10">
        <div className="text-center text-gray-400">
          <p>© 2026 Credilo. Powered by AI. Built for DSAs.</p>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
