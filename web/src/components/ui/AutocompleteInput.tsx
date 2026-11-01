import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ChangeEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { IconChevronDown } from './icons';
import selectStyles from './Select.module.scss';

interface AutocompleteInputProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  options: string[] | { value: string; label?: string }[];
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  maxLength?: number;
  hint?: string;
  error?: string;
  className?: string;
  wrapperClassName?: string;
  wrapperStyle?: React.CSSProperties;
  id?: string;
  rightElement?: ReactNode;
  variant?: 'default' | 'select';
  ariaLabel?: string;
}

export function AutocompleteInput({
  label,
  value,
  onChange,
  options,
  placeholder,
  disabled,
  required,
  maxLength,
  hint,
  error,
  className = '',
  wrapperClassName = '',
  wrapperStyle,
  id,
  rightElement,
  variant = 'default',
  ariaLabel,
}: AutocompleteInputProps) {
  const selectVariant = variant === 'select';
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputWrapRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties | null>(null);

  const normalizedOptions = options.map((opt) =>
    typeof opt === 'string'
      ? { value: opt, label: opt }
      : { value: opt.value, label: opt.label || opt.value }
  );

  const filteredOptions = normalizedOptions.filter((opt) => {
    const v = value.toLowerCase();
    return (
      opt.value.toLowerCase().includes(v) || (opt.label && opt.label.toLowerCase().includes(v))
    );
  });
  const showDropdown = isOpen && filteredOptions.length > 0 && !disabled;
  const activeIndex = highlightedIndex < filteredOptions.length ? highlightedIndex : -1;
  const listboxId = id ? `${id}-options` : undefined;

  useEffect(() => {
    if (!selectVariant || !showDropdown || activeIndex < 0 || !id) return;
    document.getElementById(`${id}-option-${activeIndex}`)?.scrollIntoView({ block: 'nearest' });
  }, [selectVariant, showDropdown, activeIndex, id]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (containerRef.current?.contains(target) || dropdownRef.current?.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useLayoutEffect(() => {
    if (!showDropdown || !inputWrapRef.current) return;
    const updateDropdownStyle = () => {
      if (!inputWrapRef.current) return;
      const rect = inputWrapRef.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom - 14;
      const height = selectVariant ? 240 : 200;
      const opensUp = spaceBelow < height && rect.top > spaceBelow;
      const width = selectVariant ? Math.min(rect.width, window.innerWidth - 16) : rect.width;
      setDropdownStyle({
        position: 'fixed',
        ...(opensUp ? { bottom: window.innerHeight - rect.top + 6 } : { top: rect.bottom + 6 }),
        left: selectVariant
          ? Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))
          : rect.left,
        width,
        maxHeight: Math.max(0, Math.min(height, opensUp ? rect.top - 14 : spaceBelow)),
        zIndex: 2010,
      });
    };
    updateDropdownStyle();
    window.addEventListener('resize', updateDropdownStyle);
    window.addEventListener('scroll', updateDropdownStyle, true);

    return () => {
      window.removeEventListener('resize', updateDropdownStyle);
      window.removeEventListener('scroll', updateDropdownStyle, true);
    };
  }, [showDropdown, selectVariant]);

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
    setIsOpen(true);
    setHighlightedIndex(-1);
  };

  const handleSelect = (selectedValue: string) => {
    onChange(selectedValue);
    setIsOpen(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (disabled) return;
    if (selectVariant && e.nativeEvent.isComposing) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        return;
      }
      setHighlightedIndex((prev) => (prev < filteredOptions.length - 1 ? prev + 1 : prev));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (selectVariant && !isOpen) setIsOpen(true);
      setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : 0));
    } else if (selectVariant && showDropdown && (e.key === 'Home' || e.key === 'End')) {
      e.preventDefault();
      setHighlightedIndex(e.key === 'Home' ? 0 : filteredOptions.length - 1);
    } else if (e.key === 'Enter') {
      if (isOpen && highlightedIndex >= 0 && highlightedIndex < filteredOptions.length) {
        e.preventDefault();
        handleSelect(filteredOptions[highlightedIndex].value);
      } else if (isOpen) {
        e.preventDefault();
        setIsOpen(false);
      }
    } else if (e.key === 'Escape') {
      if (selectVariant && showDropdown) {
        e.preventDefault();
        e.stopPropagation();
      }
      setIsOpen(false);
    } else if (e.key === 'Tab') {
      setIsOpen(false);
    }
  };

  return (
    <div className={`form-group ${wrapperClassName}`} ref={containerRef} style={wrapperStyle}>
      {label && <label htmlFor={id}>{label}</label>}
      <div style={{ position: 'relative' }} ref={inputWrapRef}>
        <input
          ref={inputRef}
          id={id}
          aria-label={ariaLabel}
          role={selectVariant ? 'combobox' : undefined}
          aria-autocomplete={selectVariant ? 'list' : undefined}
          aria-expanded={selectVariant ? showDropdown : undefined}
          aria-controls={selectVariant && showDropdown ? listboxId : undefined}
          aria-activedescendant={
            selectVariant && showDropdown && activeIndex >= 0 && id
              ? `${id}-option-${activeIndex}`
              : undefined
          }
          className={`input ${className}`.trim()}
          value={value}
          onChange={handleInputChange}
          onFocus={() => setIsOpen(true)}
          onClick={selectVariant ? () => setIsOpen(true) : undefined}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          maxLength={maxLength}
          autoComplete="off"
          style={{ paddingRight: 32 }}
        />
        {selectVariant ? (
          <button
            type="button"
            tabIndex={-1}
            disabled={disabled}
            aria-label={ariaLabel}
            aria-controls={showDropdown ? listboxId : undefined}
            aria-expanded={showDropdown}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              const nextOpen = !isOpen;
              inputRef.current?.focus({ preventScroll: true });
              setIsOpen(nextOpen);
            }}
            style={{
              position: 'absolute',
              right: 8,
              top: '50%',
              transform: 'translateY(-50%)',
              display: 'flex',
              alignItems: 'center',
              padding: 0,
              border: 0,
              background: 'transparent',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
            }}
          >
            {rightElement}
            <IconChevronDown
              size={16}
              style={{ transform: showDropdown ? 'rotate(180deg)' : undefined }}
            />
          </button>
        ) : (
          <div
            style={{
              position: 'absolute',
              right: 8,
              top: '50%',
              transform: 'translateY(-50%)',
              display: 'flex',
              alignItems: 'center',
              pointerEvents: disabled ? 'none' : 'auto',
              cursor: 'pointer',
              height: '100%',
            }}
            onClick={() => !disabled && setIsOpen(!isOpen)}
          >
            {rightElement}
            <IconChevronDown size={16} style={{ opacity: 0.5, marginLeft: 4 }} />
          </div>
        )}

        {showDropdown &&
          dropdownStyle &&
          typeof document !== 'undefined' &&
          createPortal(
            <div
              ref={dropdownRef}
              className={selectVariant ? selectStyles.dropdown : 'autocomplete-dropdown'}
              role={selectVariant ? 'listbox' : undefined}
              id={selectVariant ? listboxId : undefined}
              aria-label={selectVariant ? ariaLabel : undefined}
              style={{
                ...(selectVariant
                  ? {}
                  : {
                      backgroundColor: 'var(--bg-secondary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 'var(--radius-md)',
                      overflowY: 'auto',
                      boxShadow:
                        '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
                    }),
                ...dropdownStyle,
              }}
            >
              {filteredOptions.map((opt, index) => (
                <div
                  key={`${opt.value}-${index}`}
                  id={selectVariant && id ? `${id}-option-${index}` : undefined}
                  role={selectVariant ? 'option' : undefined}
                  aria-selected={selectVariant ? opt.value === value : undefined}
                  className={
                    selectVariant
                      ? `${selectStyles.option} ${opt.value === value ? selectStyles.optionActive : ''} ${index === activeIndex ? selectStyles.optionHighlighted : ''}`.trim()
                      : undefined
                  }
                  onMouseDown={selectVariant ? (event) => event.preventDefault() : undefined}
                  onClick={() => handleSelect(opt.value)}
                  style={
                    selectVariant
                      ? undefined
                      : {
                          padding: '8px 12px',
                          cursor: 'pointer',
                          backgroundColor:
                            index === highlightedIndex ? 'var(--bg-tertiary)' : 'transparent',
                          color: 'var(--text-primary)',
                          display: 'flex',
                          flexDirection: 'column',
                          fontSize: '0.9rem',
                        }
                  }
                  onMouseEnter={() => setHighlightedIndex(index)}
                >
                  <span style={{ fontWeight: 500 }}>{opt.value}</span>
                  {opt.label && opt.label !== opt.value && (
                    <span style={{ fontSize: '0.85em', color: 'var(--text-secondary)' }}>
                      {opt.label}
                    </span>
                  )}
                </div>
              ))}
            </div>,
            document.body
          )}
      </div>
      {hint && <div className="hint">{hint}</div>}
      {error && <div className="error-box">{error}</div>}
    </div>
  );
}
