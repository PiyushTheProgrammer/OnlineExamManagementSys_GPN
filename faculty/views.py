import os
from datetime import timezone
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from faculty.models import Faculty, Question, Course, Student, Result, ExamSpecification
import csv
import random
import json
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.contrib.auth import authenticate, login as auth_login
from django.utils.timezone import now
from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer  # type: ignore
from reportlab.lib import colors  # type: ignore
from django.db import connection
from django.contrib import messages
from faculty.forms import CSVUploadStudentForm, CSVUploadForm, FacultyRegisterForm,QuestionEditForm
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib.auth.hashers import check_password
from django.shortcuts import render, redirect
from .forms import FacultyRegisterForm
from reportlab.lib.pagesizes import letter # type: ignore
from reportlab.pdfgen import canvas # type: ignore
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.views.decorators.csrf import csrf_exempt

# Helper function to check if a user is faculty
def is_faculty(user):
    return user.groups.filter(name='Faculty').exists()


def index(request):
    return render(request,'faculty/index.html')
def about(request):
    return render(request,'faculty/about.html')
def contact(request):
    return render(request,'faculty/contact.html')

# Faculty registration view
def faculty_register(request):
    if request.method == "POST":
        form = FacultyRegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']

            # Create a Django User
            user = User.objects.create_user(username=username, email=email, password=password)
            user.save()

            # Create a Faculty profile linked to the User
            faculty = Faculty(user=user, email=email, name=username)
            faculty.save()

            # Assign the user to the Faculty group
            faculty_group = Group.objects.get(name='Faculty')
            user.groups.add(faculty_group)

            messages.success(request, "Faculty registration successful!")
            return redirect('faculty_login')
        else:
            print("❌ Form Errors:", form.errors)  # Debugging
    else:
        form = FacultyRegisterForm()

    return render(request, 'faculty/register.html', {'form': form})


# Faculty login view
def faculty_login(request):
    if request.method == "POST":
        username = request.POST.get("name")
        password = request.POST.get("password")
        print(f"📌 Username: {username}, Password: {password}")  # Debugging

        user = authenticate(request, username=username, password=password)
        if user is not None and is_faculty(user):
            auth_login(request, user)
            if not user.groups.exists():
                if hasattr(user, 'faculty'):  # Check if the user has a linked Faculty profile
                    try:
                        group = Group.objects.get(name='Faculty')
                        user.groups.add(group)
                        print(f"User {user.username} added to {group.name} group.")
                    except Group.DoesNotExist:
                        print("Faculty group does not exist.")
                        messages.error(request, "Faculty group does not exist. Please contact the administrator.")
            if user.groups.filter(name="Faculty").exists():
                messages.success(request, "Login successful!")
                return redirect("faculty_dashboard")

        else:
            messages.error(request, "Invalid credentials or not a faculty member.")

    return render(request, "faculty/login.html")


def faculty_logout(request):
    logout(request)
    return render(request,"faculty/logout.html")

# Faculty dashboard view
@login_required
@user_passes_test(is_faculty)
def faculty_dashboard(request):
    active_exams = ExamSpecification.objects.filter(is_active=True)
    active_exam_count = ExamSpecification.objects.filter(is_active=True).count()
    messages.get_messages(request)
    return render(request, "faculty/dashboard.html",{'total_exams':ExamSpecification.objects.all().count(),'total_students':Student.objects.all().count(),'active_exams':active_exams,'active_exam_count':active_exam_count,'faculty_name':request.user.username})

#faculty add student
@login_required
@user_passes_test(is_faculty, login_url='/login/')
def add_student(request):
    if request.method == "POST":
        try:
            # Get form data
            name = request.POST.get("name")
            roll_no = request.POST.get("roll_no")  # Fixed typo in Post -> POST
            course_codes = request.POST.getlist("course_codes")  # Get multiple courses
            password = roll_no  # Using roll_no as default password

            # Create User account for the student
            user = User.objects.create_user(
                username=roll_no,
                password=password
            )

            # Add user to Students group
            students_group, _ = Group.objects.get_or_create(name='Students')
            user.groups.add(students_group)

            # Create Student object
            student = Student.objects.create(
                user=user,
                name=name,
                roll_no=roll_no,
                password=password
            )

            # Add courses to student
            for course_code in course_codes:
                course = Course.objects.get(code=course_code)
                student.registered_courses.add(course)

            messages.success(request, "Student added successfully!")
            return redirect("add_student")

        except Course.DoesNotExist:
            messages.error(request, "One or more selected courses do not exist!")
        except Exception as e:
            messages.error(request, f"Error adding student: {str(e)}")

    # Get all available courses for the form
    courses = Course.objects.all()
    return render(request, "faculty/add_student.html", {'courses': courses})

# Add course view
@login_required
@user_passes_test(is_faculty)
def add_course(request):
    faculty = request.user.faculty
    courses = Course.objects.filter(faculty=faculty)

    if request.method == 'POST':
        course_name = request.POST.get('name')
        course_code = request.POST.get('code')
        year = request.POST.get('year')
        branch = request.POST.get('branch')

        Course.objects.create(
            name=course_name,
            code=course_code,
            year=year,
            branch=branch,
            faculty=faculty
        )

        messages.success(request, "Course added successfully!")
        return redirect('add_course')

    return render(request, 'faculty/add_course.html',{'courses':courses})

# Update course view
@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def update_course(request,course_id):
    course = get_object_or_404(Course,id = course_id)
    if request.method == "POST":
        course.name = request.POST.get("name")
        course.code = request.POST.get("code")
        course.save()
        messages.success(request,"Course Updated")
    return redirect("add_course")

@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def delete_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    course.delete()
    messages.success(request, "Course deleted successfully!")
    return redirect("add_course")

@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def truncate_courses(request):
    if request.method == "POST":
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("TRUNCATE TABLE faculty_course;")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        messages.success(request, "All courses have been deleted successfully!")
    return redirect("add_course")

def calculate_questions_per_unit(total_questions, marks_per_unit, total_marks):
    questions_per_unit = {}
    remaining_questions = total_questions

    # Calculate proportional questions for each unit
    for i, unit_marks in enumerate(marks_per_unit):
        unit_key = str(i + 1)  # Use consistent keys (e.g., "1", "2", etc.)
        unit_questions = round((unit_marks / total_marks) * total_questions)
        questions_per_unit[unit_key] = unit_questions
        remaining_questions -= unit_questions

    # Adjust for rounding errors
    if remaining_questions != 0:
        # Add remaining questions to the last unit
        last_unit_key = str(len(marks_per_unit))
        questions_per_unit[last_unit_key] += remaining_questions

    return questions_per_unit

@login_required
@user_passes_test(is_faculty)
def add_exam_specifications(request):
    faculty = request.user.faculty
    specifications = ExamSpecification.objects.filter(faculty=faculty)

    if request.method == "POST":
        exam_name = request.POST.get("exam_name")
        exam_type = request.POST.get("exam_type")
        num_units = int(request.POST.get("num_units"))
        course_code = request.POST.get("course_code")
        total_marks = int(request.POST.get("total_marks", 0))  # Add total marks
        total_questions = int(request.POST.get("total_questions", 0))  # Add total questions
        marks_per_unit_str = request.POST.get("marks_per_unit", "")  # Get marks per unit as a string
        max_mark = int(request.POST.get("max_mark", 1))  # Add max mark
        duration_hours = request.POST.get("duration_hours")
        duration_minutes=request.POST.get("duration_minutes")


        try:
         # Convert the question sheet string to JSON
            question_sheet_str = request.POST.get('question_sheet', '')
            question_sheet = []

                # Parse the pipe-separated string into JSON format
            for unit_str in question_sheet_str.split('|'):
                if not unit_str:
                    continue
                unit_part = unit_str.split(':')
                unit_num = int(unit_part[0].replace('Unit-', ''))
                questions = [int(mark) for mark in unit_part[1].split(',') if mark.strip()]

                question_sheet.append({
                    'unit': unit_num,
                    'questions': questions,
                    'totalMarks': sum(questions)
                })

            print("exam name",exam_name)
            print("exam type",exam_type)
            print("num_units",num_units)
            print("course_code",course_code)
            print("total_marks",total_marks)
            print("total_questions",total_questions)
            print("marks_per_unit_str",marks_per_unit_str)

            # Parse marks_per_unit from the comma-separated string
            try:
                marks_per_unit = [int(mark.strip()) for mark in marks_per_unit_str.split(",")]
            except ValueError:
                messages.error(request, "Invalid marks per unit format. Please enter comma-separated values.")
                return render(request, "faculty/add_exam_specifications.html", {'specifications': specifications})

        # Validate the number of units
            if len(marks_per_unit) != num_units:
                messages.error(request, "Number of units does not match the provided unit marks.")
                return render(request, "faculty/add_exam_specifications.html", {'specifications': specifications})

        # Calculate questions per unit dynamically
        #questions_per_unit = calculate_questions_per_unit(total_questions, marks_per_unit, total_marks)

        # Create the exam specification
            exam = ExamSpecification.objects.create(
                exam_name=exam_name,
                exam_type=exam_type,
                num_units=num_units,
                question_sheet=question_sheet,
                faculty=faculty,
                course_code=course_code,
                total_marks=total_marks,
                total_questions=total_questions,
                marks_per_unit=marks_per_unit,
                max_mark=max_mark,
                exam_duration_hours=duration_hours,
                exam_duration_minutes=duration_minutes,
            )

            messages.success(request, "Exam details saved successfully!")
            return redirect("preview_exam", exam_id=exam.id)

        except Exception as e:
            messages.error(request, f'Error saving specifications: {str(e)}')
    return render(request, "faculty/add_exam_specifications.html", {'specifications': specifications})
@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def update_specifications(request,spec_id):
    if request.method == "POST":
        spec_id = request.POST.get("spec_id")
        specification = get_object_or_404(ExamSpecification, id=spec_id)

        specification.exam_name = request.POST.get("exam_name")
        specification.exam_type = request.POST.get("exam_type")
        specification.num_units = request.POST.get("num_units")
        specification.total_marks = request.POST.get("total_marks")

        # Update exam duration fields
        specification.exam_duration_hours = int(request.POST.get("duration_hours", 1))
        specification.exam_duration_minutes = int(request.POST.get("duration_minutes", 0))

        specification.save()
        messages.success(request, "Specifications Updated Successfully")
    return redirect("add_exam_specifications")

@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def delete_exam_specification(request,spec_id):
    specification = get_object_or_404(ExamSpecification, id=spec_id)
    specification.delete()
    messages.success(request,'Specifications deleted succesfully')
    return redirect('add_exam_specifications')

@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def truncate_specifications(request):
    if request.method == "POST":
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("TRUNCATE TABLE faculty_examspecification;")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        messages.success(request, "All specifications have been deleted successfully!")
    return redirect("add_exam_specifications")

@login_required
@user_passes_test(is_faculty)
def upload_students(request):
    print("📌 upload_students function was called!")  # Debugging
    courses = Course.objects.all().order_by('name')

    if request.method == "POST":
        form = CSVUploadStudentForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['file']
            default_password = request.POST.get('default_password','').strip()
            print(f"📌 request.FILES: {request.FILES}")  # Debugging

            if not csv_file.name.endswith(".csv"):
                messages.error(request, "Please upload a valid CSV file.")
                return redirect("upload_students")
            try:
                decoded_file = csv_file.read().decode("utf-8").splitlines()
                print(f"📌 Decoded File Contents: {decoded_file}")  # Debugging
                reader = csv.reader(decoded_file)
                next(reader)  # Skip header row
                # Get or create the "Students" group
                students_group, created = Group.objects.get_or_create(name='Students')
                for row in reader:
                    print(f"📌 Processing Row: {row}")
                    roll_no = row[0].strip()
                    name = row[1].strip()
                    registered_courses = row[2].strip().split("|")  # Split courses
                    print(f"📌 Roll No: {roll_no}, Name: {name}, Registered Courses: {registered_courses}")

                    # Use custom password if provided, otherwise use roll_no
                    password = default_password if default_password else roll_no

                    # Create or get the User object
                    user, created = User.objects.get_or_create(
                        username=roll_no,
                        defaults={'password': password}
                    )

                    if not created:
                        # If user exists, update the password if it's different
                        if not user.check_password(password):
                            user.set_password(password)
                            user.save()

                    # Assign the user to the "Students" group
                    user.groups.add(students_group)

                    # Create or update the Student record
                    student, created = Student.objects.get_or_create(
                        user=user,
                        roll_no=roll_no,
                        defaults={
                            "name": name,
                            "password": password  # This is just for display
                        },
                    )

                    # Register courses
                    student.registered_courses.clear()  # Remove existing registrations
                    for course_code in registered_courses:
                        course = Course.objects.filter(code=course_code).first()
                        if course:
                            student.registered_courses.add(course)

                    student.save()
                messages.success(request, "✅ Students uploaded successfully!")
                return redirect("upload_students")
            except Exception as e:
                print(f"❌ Error: {e}")  # Print error for debugging
                messages.error(request, f"Error uploading file: {e}")
                return redirect('upload_students')

    else:
        form = CSVUploadStudentForm()



    return render(request, "faculty/upload_students.html", {"form": form,"courses":courses})

@login_required
@user_passes_test(is_faculty)
def view_students(request):
    # Get search query if exists
    search_query = request.GET.get('search', '')
      # Get all students ordered by batch then roll number
    students = Student.objects.all().order_by('registered_courses__branch', 'roll_no')

    # Apply search filter if query exists
    if search_query:
        students = students.filter(
            Q(roll_no__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(registered_courses__branch__icontains=search_query)
        ).distinct()

    context = {
        'students': students,
        'search_query': search_query,
    }
    return render(request, 'faculty/view_students.html', context)
from django.views.decorators.http import require_POST
@require_POST
def save_attendance(request):
    try:
        attendance_data = json.loads(request.POST.get('attendance_data'))

        for item in attendance_data:
            student = Student.objects.get(id=item['student_id'])
            student.attendance_status = item['status'] == 'present'
            student.save()

        return JsonResponse({'success': True, 'message': 'Attendance saved successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@login_required
@user_passes_test(is_faculty)
def update_attendance(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        status = request.POST.get('status') == 'true'

        try:
            student = Student.objects.get(id=student_id)
            student.attendance_status = status
            student.save()
            return JsonResponse({'success': True})
        except Student.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Student not found'})

    return JsonResponse({'success': False, 'error': 'Invalid request'})

@csrf_exempt
@login_required
@user_passes_test(is_faculty)
def update_student_password(request):
    if request.method == "POST":
        try:
            student_id = request.POST.get('student_id')
            new_password = request.POST.get('new_password')

            student = Student.objects.get(id=student_id)
            user = student.user

            # Update password in User model
            user.set_password(new_password)
            user.save()

            # Update display password in Student model
            student.password = new_password
            student.save()

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@csrf_exempt
@login_required
@user_passes_test(is_faculty)
def reset_student_password(request):
    if request.method == "POST":
        try:
            student_id = request.POST.get('student_id')
            student = Student.objects.get(id=student_id)

            # Reset password to roll number
            user = student.user
            user.set_password(student.roll_no)
            user.save()

            # Update student record
            student.password = student.roll_no
            student.save()

            return JsonResponse({
                'success': True,
                'message': 'Password reset to roll number'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    return JsonResponse({
        'success': False,
        'message': 'Invalid request method'
    })
from django.db import transaction
@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def truncate_students(request):
    if request.method == "POST":
        delete_option = request.POST.get('delete_option')

        try:
            if delete_option == 'all':
                # Delete all students and their associated users
                students_group = Group.objects.get(name='Students')
                student_users = User.objects.filter(groups=students_group)

                # Get count before deletion
                count = student_users.count()

                # Delete students and their users
                with transaction.atomic():
                    Student.objects.all().delete()
                    student_users.delete()

                messages.success(request, f"✅ All {count} students have been deleted successfully!")
            else:
                # Delete students from selected course only
                course_id = request.POST.get('course_id')
                if not course_id:
                    messages.error(request, "Please select a course")
                    return redirect("upload_students")

                course = Course.objects.get(id=course_id)

                # Get students registered for this course
                students = Student.objects.filter(registered_courses=course)
                user_ids = students.values_list('user_id', flat=True)

                # Get count before deletion
                count = user_ids.count()

                # Delete students and their users
                with transaction.atomic():
                    students.delete()
                    User.objects.filter(id__in=user_ids).delete()

                messages.success(request, f"✅ {count} students registered for {course.name} have been deleted successfully!")

        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error deleting students: {str(e)}")

    return redirect("upload_students")

@login_required
@user_passes_test(is_faculty)
def upload_questions(request):
    faculty = request.user.faculty
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['file']

            # Ensure correct file type
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'File format is not supported. Please upload a CSV file.')
                return redirect('upload_questions')

            try:
                # ✅ Read CSV File
                decoded_file = csv_file.read().decode('utf-8').splitlines()
                reader = csv.reader(decoded_file)
                next(reader, None)  # Skip header row safely


                # ✅ Insert Questions
                for row in reader:
                    print(f"📌 Processing Row: {row}")  # Debugging
                    if len(row) != 12:  # Ensure correct number of columns
                        messages.error(request, "Insufficient no. of columns in CSV. Please check your file.")
                        return redirect('upload_questions')

                    sr_no, name, code, question_text, option1, option2, option3, option4, correct_answer, user_c_answer, mark, unit_no = row

                    # ✅ Ensure valid Course object
                    course = Course.objects.filter(name=name.strip(), code=code.strip(), faculty=faculty).first()
                    if not course:
                        messages.error(request,f"No matching course found for {name} - {code} check your csv please")
                        continue
                    # ✅ Insert Question (EXPLICITLY SET faculty_id)
                    # print(f"📌 Inserting Question: {question_text} , Faculty id: {faculty_id}")  # Debugging
                    Question.objects.create(
                        sr_no=int(sr_no),
                        course_name=name,
                        course_code=code,
                        question_text=question_text.strip(),
                        option1=option1.strip(),
                        option2=option2.strip(),
                        option3=option3.strip(),
                        option4=option4.strip(),
                        correct_answer=correct_answer.strip(),
                        user_c_answer=user_c_answer,
                        mark=int(mark),
                        unit_no=int(unit_no),
                    )

                messages.success(request, "✅ Questions uploaded successfully!")
                return redirect('upload_questions')

            except Exception as e:
                print(f"❌ Error: {e}")  # Print error for debugging
                messages.error(request, f"Error uploading file: {e}")
                return redirect('upload_questions')

    else:
        form = CSVUploadForm()

    return render(request, 'faculty/upload_questions.html', {'form': form})

from django.db.models import Q
@login_required
@user_passes_test(is_faculty)
def manage_questions(request):
    # Handle question deletion
    if request.method == 'POST' and 'delete_question' in request.POST:
        question_id = request.POST.get('delete_question')
        try:
            question = Question.objects.get(id=question_id)
            question.delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Question deleted successfully!'})
            messages.success(request, "Question deleted successfully!")
        except Question.DoesNotExist:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'Question not found'}, status=404)
            messages.error(request, "Question not found")
        return redirect('manage_questions')

    # Handle question editing
    if request.method == 'POST' and 'question_id' in request.POST:
        question_id = request.POST.get('question_id')
        try:
            question = Question.objects.get(id=question_id)
            question.course_code = request.POST.get('course_code')
            question.question_text = request.POST.get('question_text')
            question.option1 = request.POST.get('option1')
            question.option2 = request.POST.get('option2')
            question.option3 = request.POST.get('option3')
            question.option4 = request.POST.get('option4')
            question.correct_answer = request.POST.get('correct_answer')
            question.unit_no = request.POST.get('unit_no')
            question.mark = request.POST.get('mark')
            question.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Question updated successfully!'})
            messages.success(request, "Question updated successfully!")
        except Question.DoesNotExist:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'Question not found'}, status=404)
            messages.error(request, "Question not found")
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f"Error updating question: {str(e)}")
        return redirect('manage_questions')

    # Get filter parameters from request
    course_code = request.GET.get('course_code', '')
    unit_no = request.GET.get('unit_no', '')
    search_query = request.GET.get('search', '')

    # Start with all questions
    questions = Question.objects.all()

    # Apply filters
    if course_code:
        questions = questions.filter(course_code=course_code)
    if unit_no:
        questions = questions.filter(unit_no=unit_no)
    if search_query:
        questions = questions.filter(
            Q(question_text__icontains=search_query) |
            Q(option1__icontains=search_query) |
            Q(option2__icontains=search_query) |
            Q(option3__icontains=search_query) |
            Q(option4__icontains=search_query)
        ).distinct()

    # Get distinct courses for filter dropdown
    courses = Course.objects.values_list('code', flat=True).distinct().order_by('code')

    # Get distinct units for filter dropdown
    units = Question.objects.values_list('unit_no', flat=True).distinct().order_by('unit_no')

    # Pagination
    paginator = Paginator(questions, 100)  # Show 10 questions per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'questions': page_obj,
        'courses': courses,
        'units': units,
        'course_code': course_code,
        'unit_no': unit_no,
        'search_query': search_query,
    }
    return render(request, 'faculty/manage_questions.html', context)
# Preview exam view
@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def truncate_questions(request):
    if request.method =="POST":
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("TRUNCATE TABLE faculty_question;")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            messages.success(request,"✅ All questions have been deleted successfully!")
    return redirect("upload_questions")

# Preview exam view
@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def preview_exam(request, exam_id):
    exam = ExamSpecification.objects.get(id=exam_id)
    course_code = exam.course_code
    course = Course.objects.filter(code=course_code).first()
    students = Student.objects.filter(registered_courses=course)
    print(students)

    # Check if students exist for this course
    if not students.exists():
        messages.warning(request, "No students are registered for this course.")
        # If no students are registered, check if there are existing students in the system
        existing_students = Student.objects.all()  # Fetch all students in the system
        if existing_students.exists():
            messages.warning(request, "No students are registered for this course, but there are existing students in the system.")
        else:
            messages.warning(request, "No students are registered for this course, and there are no existing students in the system.")

    # Calculate total questions from question_sheet
    total_questions = 0
    if exam.question_sheet:
        # Count the total number of questions from the question_sheet
        for unit in exam.question_sheet:
            if 'questions' in unit:
                total_questions += len(unit['questions'])

    context = {
        "exam": exam,
        "students": students,
        "course": course,
        "total_questions": total_questions,
        "question_sheet": exam.question_sheet
    }

    return render(request, "faculty/preview_exam.html", context)

# View results view
@login_required
@user_passes_test(is_faculty)
def take_exam(request):
    if not is_faculty(request.user):
        raise PermissionDenied

    if request.method == "POST":
        exam_name = request.POST.get("exam_name")
        if exam_name:
            exam = ExamSpecification.objects.filter(exam_name=exam_name).first()
            if exam:
                course = Course.objects.filter(code=exam.course_code).first()
                students = Student.objects.filter(registered_courses=course)

                try:
                    # Try to generate the JSON files
                    generate_student_json_files(exam.id, students)

                    # If successful, start the exam
                    exam.is_active = True
                    exam.start_time = now()
                    exam.save()
                    messages.success(request, f"Exam '{exam_name}' has started and JSON files have been generated!")
                except ValueError as e:
                    # Catch and display the error message
                    messages.error(request, str(e))
            else:
                messages.error(request, "Exam not found!")
        else:
            messages.error(request, "Please enter a valid exam name.")
    exams = ExamSpecification.objects.all()
    return render(request, "faculty/take_exam.html", {"exams": exams})

from django.core.exceptions import ObjectDoesNotExist

def generate_student_json_files(exam_id, students):
    # Define the directory where JSON files will be stored - handle spaces in path
    try:
        exam = ExamSpecification.objects.get(id=exam_id)
    except ExamSpecification.DoesNotExist:
        raise ValueError(f"Exam with ID {exam_id} does not exist.")

    # Define the directory where JSON files will be stored
    exam_directory = os.path.join("C:\\", f"exam_{exam_id}_{exam.exam_name.replace(' ', '_')}")
    course = Course.objects.filter(code=exam.course_code).first()

    # Create the directory if it doesn't exist
    os.makedirs(exam_directory, exist_ok=True)

    # Fetch all questions for the exam, grouped by unit
    all_questions = Question.objects.filter(course_code=exam.course_code).values(
        "id", "question_text", "option1", "option2", "option3", "option4", "correct_answer", "mark", "unit_no", "latex_equation" # latex equation added for latex equation store
    )

    if not all_questions:
        raise ValueError(f"No questions found for course code: {exam.course_code}")

    # Group questions by unit
    questions_by_unit = {}
    for question in all_questions:
        unit_no = question["unit_no"]
        if unit_no not in questions_by_unit:
            questions_by_unit[unit_no] = []
        questions_by_unit[unit_no].append(question)

    print("Questions grouped by unit:", questions_by_unit)

    # Get the exam specifications
    try:
        exam_spec = ExamSpecification.objects.get(course_code=exam.course_code, exam_name=exam.exam_name)
    except ObjectDoesNotExist:
        raise ValueError(f"No exam specifications found for course code: {exam.course_code} and exam name: {exam.exam_name}")

    print("Exam specifications - question_sheet:", exam_spec.question_sheet)

    # Generate JSON file for each student
    for student in students:
        student_data = {
            "Exam_Details": {
                "c_code": exam.course_code,
                "c_name": exam.exam_name,
                "roll_no": student.roll_no,
                "student_name": student.name,
                "year": course.year,
                "branch": course.branch,
                "m_question": exam_spec.total_questions,
                "exam_type": exam.exam_type,
                "exam_directory": exam_directory  # Store the exam directory path
            },
            "Question_Bank": []
        }

       # Step 1: Select questions based on the exam specification's question sheet
        selected_questions = []
        total_selected_marks = 0

        # Get the question distribution from the exam specification
        question_distribution = exam_spec.question_sheet  # This should be the JSON field from your model

        for unit in question_distribution:
            unit_num = unit['unit']
            if unit_num not in questions_by_unit:
                raise ValueError(f"No questions found for unit {unit_num}")

            for mark in unit['questions']:
                matching = [q for q in all_questions if q['unit_no'] == unit_num and q['mark'] == mark]
                random.shuffle(matching)
                if matching:
                    selected = matching[0]  # or random.choice(matching)
                else:
                    raise ValueError(f"No questions found for Unit {unit_num} with {mark} marks")

                selected_questions.append(selected)
                total_selected_marks += mark


        if total_selected_marks != exam_spec.total_marks:
            raise ValueError(f"Selected questions total {total_selected_marks} marks but expected {exam_spec.total_marks}")
        #print(selected_questions)
        random.shuffle(selected_questions)

        # Add the randomized questions to the JSON data
        for i, question in enumerate(selected_questions, start=1):
            question_data = {
                "q_no": i,
                "q_id": question["id"],
                "unit_no": question["unit_no"],
                "question": question["question_text"],
                "latex_equation": question.get("latex_equation", ""),  # Add LaTeX equation field
                "op1": question["option1"],
                "op2": question["option2"],
                "op3": question["option3"],
                "op4": question["option4"],
                "c_ans": question["correct_answer"],
                "user_c_ans": "",
                "marks": question["mark"],
            }
            student_data["Question_Bank"].append(question_data)

        # Write the JSON data to a file
        student_json_file = os.path.join(exam_directory, f"{student.roll_no}.json")
        with open(student_json_file, 'w') as json_file:
            json.dump(student_data, json_file, indent=4)

    return exam_directory

# View results view
@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def end_exam(request):
    if request.method == "POST":
        exam_name = request.POST.get("exam_name")
        if exam_name:
            # exam = ExamSpecification.objects.filter(exam_name=exam_name).first()
            exam = ExamSpecification.objects.filter(exam_name=exam_name).update(is_active=False, end_time=now())
            if exam:
                # exam.is_active = False
                # exam.end_time = now()
                # exam.save()
                messages.success(request, f"Exam '{exam_name}' has ended!")
            else:
                messages.error(request, "Exam not found!")
        else:
            messages.error(request, "Please enter a valid exam name.")
    return redirect('faculty_dashboard')

from reportlab.lib.pagesizes import letter # type: ignore
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle # type: ignore
from reportlab.lib import colors # type: ignore
from reportlab.lib.styles import getSampleStyleSheet # type: ignore
from .models import Result, ExamSpecification

# Add course view
@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def view_results(request):
    # Fetch all results grouped by exam
    exams = ExamSpecification.objects.all().order_by('id')
    exam_results = {}

    for exam in exams:
        results = Result.objects.filter(exam=exam).order_by('-submitted_at')
        if results.exists():
            exam_results[exam] = results

    # If the 'download' parameter is present, generate and return the PDF for a specific exam
    if request.GET.get("download") == "pdf":
        exam_id = request.GET.get("exam_id")
        if exam_id:
            try:
                exam = ExamSpecification.objects.get(id=exam_id)
                results = Result.objects.filter(exam=exam).order_by('-submitted_at')

                response = HttpResponse(content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="exam_results_{exam.exam_name}.pdf"'

                # Create a PDF document
                pdf = SimpleDocTemplate(response, pagesize=letter)
                elements = []

                # 🔹 Add Title
                styles = getSampleStyleSheet()
                title = Paragraph(f"<b><font size=16>Exam Results Report: {exam.exam_name} (Course: {exam.course_code})</font></b>", styles['Title'])
                elements.append(title)
                elements.append(Spacer(1, 12))  # Add space below title

                # Table header
                data = [
                    ["Roll No", "Name", "Total Marks", "Obtained Marks", "Percentage"]  # Table Headings
                ]

                # Add data rows for this exam
                for result in results:
                    data.append([
                        result.student.roll_no,
                        result.student.name,
                        result.total_marks,
                        result.obtained_marks,
                        f"{result.percentage:.2f}%",
                    ])

                # Create the table
                table = Table(data)

                # Apply table styles
                style = TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align all text
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold header
                    ('FONTSIZE', (0, 0), (-1, 0), 12),  # Header font size
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),  # Padding for header
                    ('FONTSIZE', (0, 1), (-1, -1), 10),  # Body font size
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)  # Table grid lines
                ])
                table.setStyle(style)

                elements.append(table)
                pdf.build(elements)  # Build and generate the PDF
                return response  # Return the generated PDF
            except ExamSpecification.DoesNotExist:
                return HttpResponse("Exam not found.", status=404)

    # If not downloading PDF, render the HTML template
    return render(request, 'faculty/view_results.html', {'exam_results': exam_results})

# Add course view
@login_required
@user_passes_test(is_faculty, login_url='/faculty_login/')
def view_student(request):
    # Fetch all students from the database
    students = Student.objects.all()
    courses = Course.objects.all()  # Fetch all courses for the dropdown
        # Initialize filter variables
    department_filter = ''
    course_filter = ''
    status_filter = ''

    # Handle POST request
    # if request.method == 'POST':
    # Get filter parameters from the request
    department_filter = request.GET.get('department', '').strip()
    course_filter = request.GET.get('course', '').strip()
    status_filter = request.GET.get('status', '').strip()

    # Apply filters if provided
    if department_filter:
    # Filter students based on the branch of their registered courses
        students = students.filter(registered_courses__branch=department_filter).distinct()

    if course_filter:
    # Filter students based on the course code of their registered courses
        students = students.filter(registered_courses__code=course_filter).distinct()

    if status_filter:
        if status_filter == "attended":
            students = students.filter(has_attempted_exam=True)
        elif status_filter == "not-attended":
            students = students.filter(has_attempted_exam=False)
        elif status_filter == "in-progress":
            students = students.filter(exam_start_time__isnull=False, has_attempted_exam=False)

    # Add branch information to each student
    for student in students:
        # Get the branch of the first registered course (or default to "Unknown")
        first_course = student.registered_courses.first()
        student.branch = first_course.branch if first_course else "Unknown"

    # Pass the students and filters to the template
    context = {
        'students': students,
        'department_filter': department_filter,
        'course_filter': course_filter,
        'status_filter': status_filter,
        'courses': courses,
        'branches': Course.BRANCH_CHOICES,  # Pass branch choices from the Course model
    }
    return render(request, 'faculty/view_student.html', context)

from django.db.models import Count, Sum,Avg,Q
@login_required
def exam_data(request):
    # Get all exams with basic statistics
    exams = ExamSpecification.objects.annotate(
        total_students=Count('result__student', distinct=True)
    ).order_by('-start_time')

    # Separate active and completed exams
    active_exams = exams.filter(is_active=True)
    completed_exams = exams.filter(is_active=False)

    # Calculate pass/fail counts for completed exams
    for exam in completed_exams:
        exam.pass_count = Result.objects.filter(
            exam=exam,
            percentage__gte=40
        ).count()
        exam.fail_count = Result.objects.filter(
            exam=exam,
            percentage__lt=40
        ).count()
        exam.avg_score = Result.objects.filter(
            exam=exam
        ).aggregate(Avg('percentage'))['percentage__avg'] or 0

    context = {
        'active_exams': active_exams,
        'completed_exams': completed_exams,
    }
    return render(request, 'faculty/exam_data.html', context)


from django.contrib.sessions.models import Session
from django.views.decorators.http import require_POST
@require_POST
@csrf_exempt
def force_logout(request, roll_no):
    try:
        student = Student.objects.get(roll_no=roll_no)
        user = student.user

        if student.exam_start_time and not student.has_attempted_exam:
            # Get all active sessions
            sessions = Session.objects.filter(expire_date__gte=timezone.now())

            # Filter sessions belonging to this user
            user_sessions = []
            for session in sessions:
                session_data = session.get_decoded()
                if '_auth_user_id' in session_data and str(session_data['_auth_user_id']) == str(user.id):
                    user_sessions.append(session.session_key)

            # Delete all sessions for this user
            Session.objects.filter(session_key__in=user_sessions).delete()

            # Preserve exam state but clear session
            student.exam_start_time = None
            student.save()

            return JsonResponse({
                'success': True,
                'message': f'Student {roll_no} has been logged out from all sessions.'
            })

        return JsonResponse({
            'success': False,
            'error': 'Student is not in an active exam session.'
        })

    except Student.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'Student with roll number {roll_no} not found.'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


from django.shortcuts import render
from django.utils import timezone

def faculty_bad_request(request, exception):
    context = {
        'error_code': '400',
        'error_message': 'Bad Request',
        'error_details': 'The server could not process your request.',
        'technical_details': {
            'timestamp': timezone.now(),
            'common_causes': [
                'Invalid form submission data',
                'Malformed file upload',
                'Invalid course or exam parameters',
                'Missing required fields in submission'
            ],
            'solutions': [
                'Verify all required fields are filled correctly',
                'Check file format and size requirements',
                'Ensure date formats are correct (YYYY-MM-DD)',
                'Validate CSV file structure before upload'
            ]
        }
    }
    return render(request, 'faculty/errors/400.html', context, status=400)

def faculty_permission_denied(request, exception):
    context = {
        'error_code': '403',
        'error_message': 'Access Forbidden',
        'error_details': 'You do not have sufficient permissions.',
        'technical_details': {
            'timestamp': timezone.now(),
            'common_causes': [
                'Session expired',
                'Invalid faculty credentials',
                'Attempting to access restricted area',
                'CSRF token verification failed'
            ],
            'solutions': [
                'Log in again with valid faculty credentials',
                'Contact system administrator for permission issues',
                'Verify your account has correct faculty privileges',
                'Do not use multiple tabs for sensitive operations'
            ]
        }
    }
    return render(request, 'faculty/errors/403.html', context, status=403)

def faculty_page_not_found(request, exception):
    context = {
        'error_code': '404',
        'error_message': 'Page Not Found',
        'error_details': 'The requested resource does not exist.',
        'technical_details': {
            'timestamp': timezone.now(),
            'common_causes': [
                'Deleted or moved resource',
                'Invalid exam or course ID',
                'Expired link',
                'Mistyped URL'
            ],
            'solutions': [
                'Verify the resource ID is correct',
                'Check if the exam/course still exists',
                'Navigate through the dashboard instead of direct URLs',
                'Contact technical support if the issue persists'
            ]
        }
    }
    return render(request, 'faculty/errors/404.html', context, status=404)

def faculty_server_error(request):
    context = {
        'error_code': '500',
        'error_message': 'Internal Server Error',
        'error_details': 'An unexpected error occurred on the server.',
        'technical_details': {
            'timestamp': timezone.now(),
            'common_causes': [
                'Database connection issues',
                'File system errors',
                'Memory allocation problems',
                'Unexpected server configuration'
            ],
            'solutions': [
                'Try the operation again after a few minutes',
                'Clear browser cache and cookies',
                'Check server logs for detailed error information',
                'Contact system administrator if the issue persists'
            ]
        }
    }
    return render(request, 'faculty/errors/500.html', context, status=500)
