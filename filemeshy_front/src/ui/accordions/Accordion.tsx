import { useState } from 'react';
import type { ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';

export interface AccordionItem {
  id: string;
  title: string;
  content: ReactNode;
  defaultOpen?: boolean;
}

export interface AccordionProps {
  items: AccordionItem[];
  allowMultiple?: boolean;
  variant?: 'default' | 'bordered' | 'separated';
  className?: string;
}

export const Accordion = ({ 
  items, 
  allowMultiple = false, 
  variant = 'default',
  className = '' 
}: AccordionProps) => {
  const [openItems, setOpenItems] = useState<Set<string>>(
    new Set(items.filter(item => item.defaultOpen).map(item => item.id))
  );

  const toggleItem = (id: string) => {
    setOpenItems(prev => {
      const newSet = new Set(allowMultiple ? prev : []);
      if (prev.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const variantClasses = {
    default: 'divide-y divide-brand-100 dark:divide-brand-900/30',
    bordered: 'border border-brand-200 dark:border-brand-800/50 rounded-lg divide-y divide-brand-100 dark:divide-brand-900/30 overflow-hidden',
    separated: 'space-y-3'
  };

  const itemClasses = {
    default: '',
    bordered: '',
    separated: 'border border-brand-200 dark:border-brand-800/50 rounded-lg overflow-hidden shadow-xs hover:shadow-md transition-shadow'
  };

  return (
    <div className={`${variantClasses[variant]} ${className}`}>
      {items.map(item => {
        const isOpen = openItems.has(item.id);
        return (
          <div key={item.id} className={itemClasses[variant]}>
            <button
              onClick={() => toggleItem(item.id)}
              className={`flex items-center justify-between w-full px-5 py-4 text-left transition-all duration-200 ${
                isOpen
                  ? 'bg-brand-50 dark:bg-brand-900/20 text-brand-900 dark:text-brand-100'
                  : 'text-gray-900 dark:text-white hover:bg-brand-50/50 dark:hover:bg-brand-900/10'
              }`}
              aria-expanded={isOpen}
            >
              <span className="font-semibold">{item.title}</span>
              <ChevronDown
                className={`w-5 h-5 transition-all duration-200 shrink-0 ml-3 ${
                  isOpen 
                    ? 'rotate-180 text-brand-600 dark:text-brand-400' 
                    : 'text-brand-500 dark:text-brand-600'
                }`}
              />
            </button>
            
            {isOpen && (
              <div className="px-5 py-4 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800/50 border-t border-brand-100 dark:border-brand-900/30">
                {item.content}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

// FAQ Accordion preconfigured
export interface FAQItem {
  question: string;
  answer: string;
}

export interface FAQAccordionProps {
  items: FAQItem[];
  className?: string;
}

export const FAQAccordion = ({ items, className = '' }: FAQAccordionProps) => {
  const accordionItems: AccordionItem[] = items.map((item, index) => ({
    id: `faq-${index}`,
    title: item.question,
    content: <p>{item.answer}</p>
  }));

  return (
    <div className={className}>
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
        Preguntas Frecuentes
      </h2>
      <Accordion items={accordionItems} variant="bordered" />
    </div>
  );
};
