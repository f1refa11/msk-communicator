(() => {
    const widget = document.getElementById('support-widget');
    if (!widget) {
        return;
    }

    const toggleButton = widget.querySelector('[data-role="toggle"]');
    const closeButton = widget.querySelector('[data-role="close"]');
    const panel = widget.querySelector('[data-role="panel"]');
    const messages = widget.querySelector('[data-role="messages"]');
    const actions = widget.querySelector('[data-role="actions"]');

    const problemOptions = [
        { key: 'video_not_opening', label: '1. не открывается видео' },
        { key: 'tutorial_not_opening', label: '2. не открывается интерактивный модуль' },
        { key: 'account_not_created', label: '3. не создаётся аккаунт' },
        { key: 'account_login_failed', label: '4. не получается зайти в аккаунт' }
    ];

    const faqMap = {
        change_password: {
            question: '1. как поменять пароль для аккаунта?',
            answer: 'Вы можете поменять пароль в настройках аккаунта. Нажмите кнопку «Перейти в настройки аккаунта» ниже и введите старый и новый пароли.'
        },
        delete_account: {
            question: '2. как удалить аккаунт?',
            answer: 'Вы можете удалить аккаунт через страницу настроек аккаунта: в самом конце страницы есть кнопка удаления.'
        }
    };

    let initialized = false;

    function setOpen(isOpen) {
        widget.classList.toggle('support-widget-open', isOpen);
        panel.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
        toggleButton.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        if (isOpen) {
            if (!initialized) {
                resetDialog();
                initialized = true;
            }
            scrollToBottom();
        }
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            messages.scrollTop = messages.scrollHeight;
        });
    }

    function addMessage(text, role) {
        const item = document.createElement('div');
        item.className = `support-widget-message support-widget-message-${role}`;
        item.textContent = text;
        messages.appendChild(item);
        scrollToBottom();
    }

    function addMessageWithLink(text, role, linkLabel, href) {
        const item = document.createElement('div');
        item.className = `support-widget-message support-widget-message-${role}`;

        const label = document.createElement('span');
        label.textContent = `${text} `;

        const link = document.createElement('a');
        link.href = href;
        link.textContent = linkLabel;
        link.className = 'support-widget-inline-link';

        item.appendChild(label);
        item.appendChild(link);
        messages.appendChild(item);
        scrollToBottom();
    }

    function clearActions() {
        actions.innerHTML = '';
    }

    function createActionButton(label, variant, onClick) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `support-widget-action support-widget-action-${variant}`;
        button.textContent = label;
        button.addEventListener('click', onClick);
        return button;
    }

    function createActionLink(label, href) {
        const link = document.createElement('a');
        link.className = 'support-widget-action support-widget-action-ghost';
        link.textContent = label;
        link.href = href;
        return link;
    }

    function setActions(items) {
        clearActions();
        for (const item of items) {
            actions.appendChild(item);
        }
    }

    function setLoadingState(isLoading) {
        actions.querySelectorAll('button').forEach((button) => {
            button.disabled = isLoading;
        });
    }

    function resetDialog() {
        messages.innerHTML = '';
        addMessage('Здравствуйте. Это чат поддержки. Выберите, что вам нужно.', 'bot');
        showRootActions();
    }

    function showRootActions() {
        setActions([
            createActionButton('Пожаловаться на проблему', 'primary', () => {
                addMessage('Пожаловаться на проблему', 'user');
                showProblemActions();
            }),
            createActionButton('Прочие вопросы', 'ghost', () => {
                addMessage('Прочие вопросы', 'user');
                showFaqActions();
            })
        ]);
    }

    function showProblemActions() {
        addMessage('Выберите одну из проблем. Я отправлю сообщение разработчикам сайта.', 'bot');

        const actionItems = problemOptions.map((problem) => {
            return createActionButton(problem.label, 'primary', async () => {
                addMessage(problem.label, 'user');
                setLoadingState(true);
                const response = await postSupport('/api/support/problem', { problem: problem.key });
                setLoadingState(false);
                addMessage(response.message, 'bot');
                showRootActions();
            });
        });

        actionItems.push(
            createActionButton('Назад', 'ghost', () => {
                addMessage('Возврат в меню', 'user');
                showRootActions();
            })
        );

        setActions(actionItems);
    }

    function showFaqActions() {
        addMessage('Выберите вопрос.', 'bot');

        setActions([
            createActionButton(faqMap.change_password.question, 'ghost', () => {
                showFaqAnswer('change_password');
            }),
            createActionButton(faqMap.delete_account.question, 'ghost', () => {
                showFaqAnswer('delete_account');
            }),
            createActionButton('Назад', 'ghost', () => {
                addMessage('Возврат в меню', 'user');
                showRootActions();
            })
        ]);
    }

    function showFaqAnswer(faqKey) {
        const faq = faqMap[faqKey];
        if (!faq) {
            addMessage('Не удалось открыть этот вопрос.', 'bot');
            showRootActions();
            return;
        }

        addMessage(faq.question, 'user');
        addMessage(faq.answer, 'bot');
        addMessageWithLink('Нажмите на эту ссылку:', 'bot', 'Перейти в настройки аккаунта', '/account/');

        setActions([
            createActionLink('Перейти в настройки аккаунта', '/account/'),
            createActionButton('Всё получилось', 'primary', async () => {
                await submitFaqFeedback(faqKey, 'resolved', 'Всё получилось');
            }),
            createActionButton('Возникли проблемы', 'ghost', async () => {
                await submitFaqFeedback(faqKey, 'issues', 'Возникли проблемы');
            }),
            createActionButton('Назад', 'ghost', () => {
                showFaqActions();
            })
        ]);
    }

    async function submitFaqFeedback(faqKey, feedback, label) {
        addMessage(label, 'user');
        setLoadingState(true);
        const response = await postSupport('/api/support/faq_feedback', {
            faq: faqKey,
            feedback: feedback
        });
        setLoadingState(false);
        addMessage(response.message, 'bot');
        showRootActions();
    }

    async function postSupport(url, payload) {
        const body = new URLSearchParams(payload);
        body.set('source', 'widget');

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Support-Widget': '1'
                },
                body: body.toString()
            });

            const contentType = response.headers.get('Content-Type') || '';
            if (contentType.includes('application/json')) {
                const data = await response.json();
                return {
                    ok: Boolean(data.ok),
                    message: data.message || (data.ok ? 'Сообщение отправлено.' : 'Ошибка отправки.')
                };
            }

            return {
                ok: response.ok,
                message: response.ok ? 'Сообщение отправлено разработчикам сайта.' : 'Не удалось отправить сообщение. Попробуйте снова.'
            };
        } catch (error) {
            return {
                ok: false,
                message: 'Не удалось отправить сообщение. Проверьте подключение и попробуйте снова.'
            };
        }
    }

    toggleButton.addEventListener('click', () => {
        const isOpen = widget.classList.contains('support-widget-open');
        setOpen(!isOpen);
    });

    closeButton.addEventListener('click', () => {
        setOpen(false);
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && widget.classList.contains('support-widget-open')) {
            setOpen(false);
        }
    });
})();

(() => {
    const NON_DIGIT_RE = /\D/g;

    function isDigit(char) {
        return /\d/.test(char || '');
    }

    function extractDigits(value) {
        return String(value || '').replace(NON_DIGIT_RE, '');
    }

    function normalizeDigits(value) {
        let digits = extractDigits(value);
        if (!digits) {
            return '';
        }

        if (digits.length > 11) {
            digits = digits.slice(0, 11);
        }

        if (digits[0] === '8') {
            digits = `7${digits.slice(1)}`;
        } else if (digits[0] === '9') {
            digits = `7${digits}`;
            if (digits.length > 11) {
                digits = digits.slice(0, 11);
            }
        }

        return digits;
    }

    function formatPhone(value) {
        const digits = normalizeDigits(value);
        if (!digits) {
            return '';
        }

        const country = digits.slice(0, 1);
        const part1 = digits.slice(1, 4);
        const part2 = digits.slice(4, 7);
        const part3 = digits.slice(7, 9);
        const part4 = digits.slice(9, 11);

        let formatted = `+${country}`;
        if (part1) {
            formatted += ` (${part1}`;
        }
        if (part1.length === 3) {
            formatted += ')';
        }
        if (part2) {
            formatted += ` ${part2}`;
        }
        if (part3) {
            formatted += `-${part3}`;
        }
        if (part4) {
            formatted += `-${part4}`;
        }
        return formatted;
    }

    function isValidPhone(value) {
        const digits = extractDigits(value);
        return digits.length === 11 && digits[0] === '7';
    }

    function countDigitsBefore(value, caretPosition) {
        const safeCaret = Math.max(0, Number(caretPosition) || 0);
        return extractDigits(String(value || '').slice(0, safeCaret)).length;
    }

    function findCaretByDigitIndex(formattedValue, digitIndex) {
        if (digitIndex <= 0) {
            return 0;
        }

        let seenDigits = 0;
        for (let i = 0; i < formattedValue.length; i += 1) {
            if (!isDigit(formattedValue[i])) {
                continue;
            }
            seenDigits += 1;
            if (seenDigits >= digitIndex) {
                return i + 1;
            }
        }

        return formattedValue.length;
    }

    function findPrevDigitIndex(value, fromIndexExclusive) {
        for (let i = fromIndexExclusive - 1; i >= 0; i -= 1) {
            if (isDigit(value[i])) {
                return i;
            }
        }
        return -1;
    }

    function findNextDigitIndex(value, fromIndexInclusive) {
        for (let i = fromIndexInclusive; i < value.length; i += 1) {
            if (isDigit(value[i])) {
                return i;
            }
        }
        return -1;
    }

    function initPhoneValidation(formId, inputId, errorId) {
        const form = document.getElementById(formId);
        const phoneInput = document.getElementById(inputId);
        if (!form || !phoneInput) {
            return;
        }

        const submitButton = form.querySelector('button[type="submit"]');
        const errorNode = document.getElementById(errorId);

        function applyFormattedValue(rawValue, digitCaretIndex, showError) {
            const formattedValue = formatPhone(rawValue);
            phoneInput.value = formattedValue;

            if (typeof digitCaretIndex === 'number' && document.activeElement === phoneInput) {
                const maxDigits = extractDigits(formattedValue).length;
                const safeDigitIndex = Math.max(0, Math.min(digitCaretIndex, maxDigits));
                const caretPosition = findCaretByDigitIndex(formattedValue, safeDigitIndex);
                phoneInput.setSelectionRange(caretPosition, caretPosition);
            }

            const hasInput = extractDigits(phoneInput.value).length > 0;
            const isValid = isValidPhone(phoneInput.value);

            if (submitButton) {
                submitButton.disabled = !isValid;
                submitButton.classList.toggle('disabled', !isValid);
            }

            if (errorNode) {
                if (showError && hasInput && !isValid) {
                    errorNode.textContent = 'Введите номер в формате +7 (900) 123-45-67.';
                } else {
                    errorNode.textContent = '';
                }
            }

            return isValid;
        }

        function updatePhoneState(showError) {
            const selectionStart = phoneInput.selectionStart ?? phoneInput.value.length;
            const digitCaretIndex = countDigitsBefore(phoneInput.value, selectionStart);
            return applyFormattedValue(phoneInput.value, digitCaretIndex, showError);
        }

        phoneInput.addEventListener('keydown', (event) => {
            if (event.key !== 'Backspace' && event.key !== 'Delete') {
                return;
            }

            const selectionStart = phoneInput.selectionStart ?? 0;
            const selectionEnd = phoneInput.selectionEnd ?? selectionStart;
            if (selectionStart !== selectionEnd) {
                return;
            }

            const currentValue = phoneInput.value;
            if (!currentValue) {
                return;
            }

            if (event.key === 'Backspace' && selectionStart > 0) {
                const charBefore = currentValue.charAt(selectionStart - 1);
                if (!isDigit(charBefore)) {
                    const removeDigitIndex = findPrevDigitIndex(currentValue, selectionStart - 1);
                    if (removeDigitIndex >= 0) {
                        event.preventDefault();
                        const nextRawValue =
                            currentValue.slice(0, removeDigitIndex) +
                            currentValue.slice(removeDigitIndex + 1);
                        const nextDigitIndex = countDigitsBefore(nextRawValue, removeDigitIndex);
                        applyFormattedValue(nextRawValue, nextDigitIndex, false);
                    }
                }
                return;
            }

            if (event.key === 'Delete' && selectionStart < currentValue.length) {
                const charAtCaret = currentValue.charAt(selectionStart);
                if (!isDigit(charAtCaret)) {
                    const removeDigitIndex = findNextDigitIndex(currentValue, selectionStart + 1);
                    if (removeDigitIndex >= 0) {
                        event.preventDefault();
                        const nextRawValue =
                            currentValue.slice(0, removeDigitIndex) +
                            currentValue.slice(removeDigitIndex + 1);
                        const nextDigitIndex = countDigitsBefore(currentValue, selectionStart);
                        applyFormattedValue(nextRawValue, nextDigitIndex, false);
                    }
                }
            }
        });

        phoneInput.addEventListener('input', () => {
            updatePhoneState(false);
        });

        phoneInput.addEventListener('blur', () => {
            updatePhoneState(true);
        });

        form.addEventListener('submit', (event) => {
            if (!updatePhoneState(true)) {
                event.preventDefault();
                phoneInput.focus();
            }
        });

        applyFormattedValue(phoneInput.value, countDigitsBefore(phoneInput.value, phoneInput.value.length), false);
    }

    initPhoneValidation('reg_form', 'tel', 'tel-error');
    initPhoneValidation('login_form', 'login-tel', 'login-tel-error');
    initPhoneValidation('account-tel-form', 'account-tel', 'account-tel-error');
})();
